"""Client per login e lettura dati dal portale clienti LIRCA.

Flusso (ricavato analizzando il traffico reale del portale):
  1. GET  /index.php                 -> cookie PHPSESSID iniziale
  2. POST /index-process.php         -> login (username, password)
  3. GET  /home-page.php?username=.. -> contiene i link con codstab/codut/codut2
  4. GET  /gestione-calore.php?...   -> tabella con i contatori e le ultime letture
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

                matricola = cells[5].get_text(strip=True)
                if not matricola or not matricola.isdigit():
                    continue

                readings.append(
                    LircaReading(
                        tipo=cells[0].get_text(strip=True),
                        data_lettura=cells[2].get_text(strip=True),
                        ultima_lettura=cells[3].get_text(strip=True),
                        ubicazione=cells[4].get_text(strip=True),
                        matricola=matricola,
                    )
                )
            break

        _LOGGER.debug("Trovati %d contatori", len(readings))
        return readings

    async def async_fetch_all(self) -> list[LircaReading]:
        """Esegue l'intero flusso: login + estrazione parametri + lettura contatori."""
        username_token = await self.async_login()
        await self.async_get_meter_params(username_token)
        return await self.async_get_readings()
