#!/usr/bin/env python3
"""Sonde de confinement réseau exécutée à la demande dans ``iryx-analysis``.

La sonde tente une unique connexion TCP vers une adresse publique. Dans un
conteneur ``network_mode: none``, le noyau refuse la connexion avec ``ENETUNREACH``
(``Network is unreachable`` en anglais) : c'est la seule issue attendue. La
validation porte sur l'errno, jamais sur le libellé localisé. Aucun autre hôte,
aucune nouvelle tentative et aucun repli ne sont autorisés.
"""

from __future__ import annotations

import errno
import socket
import sys
from collections.abc import Callable

TARGET_HOST = "1.1.1.1"
TARGET_PORT = 443
TIMEOUT_SECONDS = 3
EXPECTED_ERROR = "Network is unreachable"

Connector = Callable[[tuple[str, int], float], socket.socket]


def probe_external_tcp(connector: Connector | None = None) -> None:
    """Tenter la sonde ; toute erreur réseau est levée à l'appelant."""
    connect = connector or socket.create_connection
    connection = connect((TARGET_HOST, TARGET_PORT), TIMEOUT_SECONDS)
    connection.close()


def main() -> int:
    """Valider que la sortie TCP est bloquée avec l'errno attendu."""
    try:
        probe_external_tcp()
    except OSError as exc:
        if exc.errno != errno.ENETUNREACH:
            print(
                f"ERREUR: blocage réseau inattendu vers {TARGET_HOST}:{TARGET_PORT}: {exc} ; "
                f"attendu: errno {errno.ENETUNREACH} ({EXPECTED_ERROR}).",
                file=sys.stderr,
            )
            return 1
        print(
            f"OK: TCP externe vers {TARGET_HOST}:{TARGET_PORT} bloqué "
            f"(errno {errno.ENETUNREACH} : {exc})."
        )
        return 0

    print(
        f"ERREUR: une connexion TCP vers {TARGET_HOST}:{TARGET_PORT} a réussi ; "
        "l'isolation réseau n'est pas effective.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
