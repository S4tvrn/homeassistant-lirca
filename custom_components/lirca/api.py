"""Client per login e lettura dati dal portale clienti LIRCA.

Flusso (ricavato analizzando il traffico reale del portale):
  1. GET  /index.php                 -> cookie PHPSESSID iniziale
  2. POST /index-process.php         -> login (username, password)
  3. GET  /home-page.php?username=..        -> contiene i link con codstab/codut/codut2
  4. GET  /gestione-calore.php?...          -> tabella contatori calore/ACS e ultime letture
  5. GET  /contatori-letture.php?...        -> tabella contatori acqua Fredda/Calda e ultime letture
  6. GET  /storico-letture-calore.php?...   -> storico consumi per singolo dispositivo calore/ACS
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass

import aiohttp
from bs4 import BeautifulSoup

from .const import BASE_URL, HEADERS_COMMON

_LOGGER = logging.getLogger(__name__)


class LircaAuthError(Exception):
    """Credenziali errate o login fallito."""


class LircaConnectionError(Exception):
    """Errore di rete o portale non raggiungibile."""


@dataclass
class LircaReading:
    """Una singola lettura di un contatore."""

    tipo: str
    ubicazione: str
    matricola: str
    data_lettura: str
    ultima_lettura: str
    # Presenti solo per i contatori calore/ACS: identificano il dispositivo
    # su storico-letture-calore.php (assenti per i contatori acqua).
    progr: str | None = None
    rk: str | None = None


@dataclass
class LircaHistoryEntry:
    """Una riga dello storico consumi di un dispositivo calore/ACS."""

    tipo_consumo: str
    data_doc: str
    data_lettura_precedente: str
    data_lettura_attuale: str
    lettura_precedente: str
    lettura_attuale: str
    consumo: str


class LircaApiClient:
    """Wrapper asincrono per il portale LIRCA."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._meter_params: dict[str, str] | None = None

    async def async_login(self) -> str:
        """Esegue il login e restituisce il token 'username' codificato usato nell'URL."""
        try:
            # 1. Pagina iniziale: ottiene il cookie di sessione PHPSESSID
            async with self._session.get(f"{BASE_URL}/index.php", headers=HEADERS_COMMON) as resp:
                resp.raise_for_status()

            # 2. Login vero e proprio (chiamata AJAX)
            login_headers = {
                **HEADERS_COMMON,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/index.php",
            }
            payload = {"username": self._username, "password": self._password}
            async with self._session.post(
                f"{BASE_URL}/index-process.php", data=payload, headers=login_headers
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise LircaConnectionError(str(err)) from err

        match = re.search(r"username=([^'\"&]+)", text)
        if not match:
            raise LircaAuthError("Login fallito: credenziali errate o formato risposta cambiato")

        return match.group(1)

    async def async_get_meter_params(self, username_token: str) -> dict[str, str]:
        """Estrae codstab/codut/codut2 dalla home page post-login."""
        try:
            async with self._session.get(
                f"{BASE_URL}/home-page.php",
                params={"username": username_token},
                headers=HEADERS_COMMON,
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise LircaConnectionError(str(err)) from err

        codstab = re.search(r"codstab=([^&\"]+)", text)
        codut = re.search(r"codut=([^&\"]+)", text)
        codut2 = re.search(r"codut2=([^&\"]+)", text)

        if not (codstab and codut and codut2):
            raise LircaConnectionError("Impossibile trovare i parametri utenza nella home page")

        self._meter_params = {
            "username": username_token,
            "codstab": codstab.group(1),
            "codut": codut.group(1),
            "codut2": codut2.group(1),
        }
        return self._meter_params

    async def async_get_readings(self) -> list[LircaReading]:
        """Scarica gestione-calore.php e ne estrae la tabella dei contatori."""
        if self._meter_params is None:
            raise LircaConnectionError("async_get_meter_params non ancora chiamato")

        try:
            async with self._session.get(
                f"{BASE_URL}/gestione-calore.php",
                params=self._meter_params,
                headers=HEADERS_COMMON,
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise LircaConnectionError(str(err)) from err

        soup = BeautifulSoup(text, "html.parser")
        readings: list[LircaReading] = []

        for table in soup.find_all("table"):
            headers_txt = [th.get_text(strip=True) for th in table.find_all("th")]
            if not any("Ultima" in h for h in headers_txt):
                continue

            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue

                tipo = cells[0].get_text(strip=True)
                ubicazione = cells[4].get_text(strip=True)
                matricola = cells[5].get_text(strip=True)
                if not matricola or matricola == "-":
                    # L'ACS non ha una matricola propria sul portale: usiamo
                    # tipo+ubicazione come identificativo univoco del dispositivo.
                    matricola = f"{tipo}-{ubicazione}".strip("-")
                if not matricola:
                    continue

                # Ogni riga linka storico-letture-calore.php con progr/rk del dispositivo.
                row_html = str(row)
                progr_match = re.search(r"progr=([^&\"']+)", row_html)
                rk_match = re.search(r"rk=([^&\"']+)", row_html)

                readings.append(
                    LircaReading(
                        tipo=tipo,
                        data_lettura=cells[2].get_text(strip=True),
                        ultima_lettura=cells[3].get_text(strip=True),
                        ubicazione=ubicazione,
                        matricola=matricola,
                        progr=progr_match.group(1) if progr_match else None,
                        rk=rk_match.group(1) if rk_match else None,
                    )
                )

        _LOGGER.debug("Trovati %d contatori", len(readings))
        return readings

    async def async_get_water_readings(self) -> list[LircaReading]:
        """Scarica contatori-letture.php e ne estrae la tabella acqua Fredda/Calda."""
        if self._meter_params is None:
            raise LircaConnectionError("async_get_meter_params non ancora chiamato")

        try:
            async with self._session.get(
                f"{BASE_URL}/contatori-letture.php",
                params=self._meter_params,
                headers=HEADERS_COMMON,
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise LircaConnectionError(str(err)) from err

        soup = BeautifulSoup(text, "html.parser")
        readings: list[LircaReading] = []

        for table in soup.find_all("table"):
            headers_txt = [th.get_text(strip=True) for th in table.find_all("th")]
            if not any("Matricola" in h for h in headers_txt):
                continue

            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 11:
                    continue

                # La colonna "Matricola" (indice 2) è sempre "-" su questa pagina:
                # l'id reale del contatore è in un <td class="d-none"> in coda alla riga.
                matricola = cells[10].get_text(strip=True)
                if not matricola or not matricola.isdigit():
                    continue

                readings.append(
                    LircaReading(
                        tipo=cells[0].get_text(strip=True),
                        matricola=matricola,
                        ubicazione=cells[3].get_text(strip=True),
                        data_lettura=cells[5].get_text(strip=True),
                        ultima_lettura=cells[6].get_text(strip=True),
                    )
                )

        _LOGGER.debug("Trovati %d contatori acqua", len(readings))
        return readings

    async def async_get_heat_history(self, reading: LircaReading) -> list[LircaHistoryEntry]:
        """Scarica storico-letture-calore.php per un dispositivo calore/ACS.

        Richiede che `reading` provenga da `async_get_readings` (deve avere
        `progr`/`rk` valorizzati). I contatori acqua non hanno questa pagina.
        """
        if self._meter_params is None:
            raise LircaConnectionError("async_get_meter_params non ancora chiamato")
        if not reading.progr or not reading.rk:
            raise LircaConnectionError("La reading non ha progr/rk: non è un dispositivo calore/ACS")

        params = {**self._meter_params, "progr": reading.progr, "rk": reading.rk}

        try:
            async with self._session.get(
                f"{BASE_URL}/storico-letture-calore.php",
                params=params,
                headers=HEADERS_COMMON,
            ) as resp:
                resp.raise_for_status()
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise LircaConnectionError(str(err)) from err

        soup = BeautifulSoup(text, "html.parser")
        history: list[LircaHistoryEntry] = []

        for table in soup.find_all("table"):
            headers_txt = [th.get_text(strip=True) for th in table.find_all("th")]
            if not any("Consumo" in h for h in headers_txt):
                continue

            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 8:
                    continue

                data_doc = cells[2].get_text(strip=True)
                if not data_doc:
                    continue

                history.append(
                    LircaHistoryEntry(
                        tipo_consumo=cells[0].get_text(strip=True),
                        data_doc=data_doc,
                        data_lettura_precedente=cells[3].get_text(strip=True),
                        data_lettura_attuale=cells[4].get_text(strip=True),
                        lettura_precedente=cells[5].get_text(strip=True),
                        lettura_attuale=cells[6].get_text(strip=True),
                        consumo=cells[7].get_text(strip=True),
                    )
                )
            break

        _LOGGER.debug(
            "Trovate %d righe di storico per il dispositivo %s", len(history), reading.matricola
        )
        return history

    async def async_fetch_all(self) -> list[LircaReading]:
        """Esegue l'intero flusso: login + estrazione parametri + lettura contatori."""
        username_token = await self.async_login()
        await self.async_get_meter_params(username_token)
        heat_readings = await self.async_get_readings()
        water_readings = await self.async_get_water_readings()
        return heat_readings + water_readings
