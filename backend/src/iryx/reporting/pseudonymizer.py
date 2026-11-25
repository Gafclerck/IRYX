"""Module de pseudonymisation déterministe (Story 8.1, FR25, D-19, NFR-SEC-07).

Basé sur Microsoft Presidio (``presidio-analyzer`` / ``presidio-anonymizer``), ce
module détecte les identifiants techniques via quatre ``PatternRecognizer``
déterministes et les remplace par des pseudonymes stables, propres à chaque dossier.

La table de correspondances n'est jamais stockée en clair : son état canonique est
un jeton Fernet chiffré avec une clé dérivée de ``Settings.secret_key`` et du
``case_id``. Ce jeton est la seule représentation portable d'une table et ne quitte
jamais le serveur.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import re
import threading
import uuid
from collections.abc import Callable
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from presidio_anonymizer.operators import Operator, OperatorType

from iryx.core.config import get_settings
from iryx.reporting.schemas import (
    DetectedEntityInfo,
    PseudonymizeRequest,
    PseudonymizeResult,
)

__all__ = [
    "CasePseudonymStore",
    "DeterministicPseudonymizer",
    "PseudonymStoreError",
    "SUPPORTED_ENTITY_TYPES",
]

SUPPORTED_ENTITY_TYPES: tuple[str, ...] = (
    "IP_ADDRESS",
    "HOSTNAME",
    "USER_ACCOUNT",
    "EMAIL_ADDRESS",
)

# Presidio 2.2.35 (version plancher) n'expose ni ``add_anonymizer`` ni le paramètre
# ``merge_entities_with_spaces``. Les détecter une fois permet de rester compatible
# avec le plancher comme avec les versions récentes sans dupliquer le code.
_HAS_ADD_ANONYMIZER = hasattr(AnonymizerEngine, "add_anonymizer")
_ANONYMIZE_SUPPORTS_MERGE_SPACES = (
    "merge_entities_with_spaces" in inspect.signature(AnonymizerEngine.anonymize).parameters
)

# --- Règles de détection déterministes ----------------------------------------------

_IP_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IP_ADDRESS_PATTERN = rf"(?<!\d)(?<!\d\.)(?:{_IP_OCTET}\.){{3}}{_IP_OCTET}(?!\d)(?!\.\d)"

# Noms d'hôtes Windows : préfixe machine reconnu (ou code majuscule), au moins un
# chiffre et un tiret, et 15 caractères maximum. La contrainte sur le préfixe évite
# de pseudonymiser des identifiants neutres tels que ``NFR-SEC-07``.
_HOST_FIRST_SEGMENT = (
    r"(?:SRV|SRVR|SERVER|MACHINE|NODE|COMPUTER|DC|AD|WIN|WKS|WS|PC|CLT|LT|DESKTOP|"
    r"HOST|HOSTNAME|HST|FS|SQL|APP|WEB|MBX|CAS|LDAP|RDP|VM|EXCH|DMZ|PRX|FW|RT|SW|"
    r"NAS|DNS|DHCP|(?-i:[A-Z]{1,6}\d{1,4}))"
)
HOSTNAME_PATTERN = (
    r"(?<![A-Za-z0-9_.\-])"
    r"(?=[A-Za-z0-9-]{3,15}(?![A-Za-z0-9_\-]))"
    r"(?=[A-Za-z0-9-]*\d)" + _HOST_FIRST_SEGMENT + r"(?:-[A-Za-z0-9]+)+"
    r"(?![A-Za-z0-9_\-])"
)

# Comptes techniques : ``admin_ad`` ou ``DOMAIN\account``. Les jetons déjà
# pseudonymisés sont explicitement exclus pour garder les écritures idempotentes.
USER_ACCOUNT_PATTERN = (
    r"(?<![A-Za-z0-9_.\-])"
    r"(?!IP_INTERNAL_|HOST_SERVER_|USER_ACCOUNT_|EMAIL_ADDRESS_)"
    r"(?:[A-Za-z][A-Za-z0-9-]*\\[A-Za-z0-9._-]+"
    r"|[A-Za-z][A-Za-z0-9._-]*_[A-Za-z0-9._-]+)"
    r"(?![A-Za-z0-9_.\-])"
)

EMAIL_ADDRESS_PATTERN = (
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9.\-]*[A-Za-z0-9])?\.[A-Za-z]{2,}"
    r"(?![A-Za-z0-9\-])"
)

_PSEUDONYM_INDEX_PATTERNS: dict[str, re.Pattern[str]] = {
    "IP_ADDRESS": re.compile(r"^IP_INTERNAL_(\d+)$"),
    "HOSTNAME": re.compile(r"^HOST_SERVER_(\d+)$"),
    "USER_ACCOUNT": re.compile(r"^USER_ACCOUNT_([A-Z]+)$"),
    "EMAIL_ADDRESS": re.compile(r"^EMAIL_ADDRESS_(\d+)$"),
}


def _normalize_case_id(value: str | uuid.UUID) -> str:
    """Retourne un identifiant de dossier stable sous forme de chaîne."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError("Le case_id doit être un UUID ou une chaîne non vide.")


def _letters_from_index(index: int) -> str:
    """Convertit un compteur basé sur 1 en lettres majuscules (1 -> A, 27 -> AA)."""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _index_from_letters(letters: str) -> int:
    """Convertit des lettres majuscules en compteur basé sur 1 (A -> 1, AA -> 27)."""
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _format_pseudonym(entity_type: str, index: int) -> str:
    """Formate le pseudonyme d'un type d'entité pour un compteur donné."""
    if entity_type == "IP_ADDRESS":
        return f"IP_INTERNAL_{index}"
    if entity_type == "HOSTNAME":
        return f"HOST_SERVER_{index:02d}"
    if entity_type == "USER_ACCOUNT":
        return f"USER_ACCOUNT_{_letters_from_index(index)}"
    if entity_type == "EMAIL_ADDRESS":
        return f"EMAIL_ADDRESS_{index}"
    raise PseudonymStoreError("Type d'entité non pris en charge par le magasin.")


def _index_from_pseudonym(entity_type: str, pseudonym: str) -> int:
    """Récupère le compteur encodé dans un pseudonyme (0 s'il est inconnu)."""
    pattern = _PSEUDONYM_INDEX_PATTERNS.get(entity_type)
    if pattern is None:
        return 0
    match = pattern.fullmatch(pseudonym)
    if not match:
        return 0
    raw = match.group(1)
    return _index_from_letters(raw) if entity_type == "USER_ACCOUNT" else int(raw)


def _recompute_counters(mappings: dict[str, dict[str, str]]) -> dict[str, int]:
    """Recalcule les compteurs depuis le magasin chiffré, jamais depuis la mémoire."""
    counters = {entity_type: 0 for entity_type in SUPPORTED_ENTITY_TYPES}
    for entity_type, bucket in mappings.items():
        for pseudonym in bucket.values():
            index = _index_from_pseudonym(entity_type, pseudonym)
            if index > counters.get(entity_type, 0):
                counters[entity_type] = index
    return counters


class PseudonymStoreError(Exception):
    """Erreur contrôlée pour une table de correspondances illisible ou invalide."""


class CasePseudonymStore:
    """Table de correspondances chiffrée et isolée par dossier.

    Le jeton Fernet est l'état canonique. Chaque mutation déchiffre le JSON complet,
    applique la modification puis le rechiffre ; les compteurs sont toujours déduits
    des pseudonymes stockés afin qu'un jeton restauré conserve la même numérotation.
    """

    _VERSION = 1
    _KEY_CONTEXT = b"iryx:pseudonymisation:v1|"

    def __init__(
        self,
        case_id: str | uuid.UUID,
        secret_key: str | None = None,
        token: str | bytes | None = None,
    ) -> None:
        self.case_id = _normalize_case_id(case_id)
        resolved_key = secret_key if secret_key is not None else get_settings().secret_key
        if not resolved_key:
            raise ValueError("La clé secrète de pseudonymisation ne peut pas être vide.")
        self._key = self.derive_key(self.case_id, resolved_key)
        self._fernet = Fernet(self._key)
        # Le jeton canonique est muté par une séquence déchiffrer→modifier→chiffrer.
        # Un verrou réentrant garantit qu'un accès concurrent sur le même dossier
        # ne puisse pas écraser une correspondance venant d'être attribuée.
        self._lock = threading.RLock()
        self._token: bytes | None = None
        if token is not None:
            self.import_token(token)

    @staticmethod
    def derive_key(case_id: str | uuid.UUID, secret_key: str) -> bytes:
        """Dérive une clé Fernet propre au dossier depuis le secret applicatif."""
        normalized = _normalize_case_id(case_id)
        material = (
            CasePseudonymStore._KEY_CONTEXT
            + normalized.encode("utf-8")
            + b"|"
            + secret_key.encode("utf-8")
        )
        return base64.urlsafe_b64encode(hashlib.sha256(material).digest())

    @property
    def has_mappings(self) -> bool:
        """Indique si au moins un pseudonyme a été attribué."""
        with self._lock:
            return any(self._read_state().values())

    def export_token(self) -> str:
        """Exporte l'état canonique chiffré sous forme de jeton Fernet ASCII."""
        with self._lock:
            if self._token is None:
                return self._encrypt_state({}).decode("ascii")
            return self._token.decode("ascii")

    def import_token(self, token: str | bytes) -> None:
        """Importe et valide un jeton chiffré, ou lève PseudonymStoreError."""
        with self._lock:
            try:
                raw = token.encode("ascii") if isinstance(token, str) else bytes(token)
                self._fernet.decrypt(raw)
            except (InvalidToken, TypeError, ValueError, UnicodeEncodeError):
                raise PseudonymStoreError(
                    "Jeton de pseudonymisation invalide ou corrompu."
                ) from None

            previous = self._token
            self._token = raw
            try:
                self._read_state()
            except PseudonymStoreError:
                self._token = previous
                raise

    def get_pseudonym(self, entity_type: str, original_value: str) -> str:
        """Retourne le pseudonyme stable d'une valeur, en l'attribuant à la première utilisation."""
        if entity_type not in SUPPORTED_ENTITY_TYPES:
            raise PseudonymStoreError("Type d'entité non pris en charge par le magasin.")
        if not isinstance(original_value, str) or not original_value:
            raise PseudonymStoreError("Valeur d'entité invalide.")

        with self._lock:
            mappings = self._read_state()
            bucket = mappings.setdefault(entity_type, {})
            existing = bucket.get(original_value)
            if existing is not None:
                return existing

            counters = _recompute_counters(mappings)
            index = counters.get(entity_type, 0) + 1
            used = set(bucket.values())
            pseudonym = _format_pseudonym(entity_type, index)
            while pseudonym in used:
                index += 1
                pseudonym = _format_pseudonym(entity_type, index)
            bucket[original_value] = pseudonym
            self._write_state(mappings)
            return pseudonym

    def get_original(self, pseudonym: str) -> str | None:
        """Retourne la valeur d'origine d'un pseudonyme, si elle existe dans ce dossier."""
        with self._lock:
            for bucket in self._read_state().values():
                for original, assigned in bucket.items():
                    if assigned == pseudonym:
                        return original
            return None

    def depseudonymize(self, text: str) -> str:
        """Restaure les valeurs d'origine à partir des pseudonymes présents dans le texte."""
        with self._lock:
            mappings = self._read_state()
        pairs = [
            (pseudonym, original)
            for bucket in mappings.values()
            for original, pseudonym in bucket.items()
        ]
        if not pairs:
            raise PseudonymStoreError("Aucune table de correspondances disponible pour ce dossier.")

        pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
        reverse = dict(pairs)
        pattern = re.compile(
            r"(?<!\w)(?:" + "|".join(re.escape(pseudonym) for pseudonym, _ in pairs) + r")(?!\w)"
        )
        return pattern.sub(lambda match: reverse[match.group(0)], text)

    def _read_state(self) -> dict[str, dict[str, str]]:
        """Déchiffre et valide l'état JSON canonique."""
        if self._token is None:
            return {}
        try:
            plaintext = self._fernet.decrypt(self._token).decode("utf-8")
            payload: Any = json.loads(plaintext)
        except (InvalidToken, UnicodeDecodeError, ValueError):
            raise PseudonymStoreError("Jeton de pseudonymisation invalide ou corrompu.") from None

        if not isinstance(payload, dict):
            raise PseudonymStoreError("Table de correspondances invalide pour ce dossier.")
        if payload.get("version") != self._VERSION:
            raise PseudonymStoreError("Version de la table de correspondances non prise en charge.")
        if payload.get("case_id") != self.case_id:
            raise PseudonymStoreError("Table de correspondances invalide pour ce dossier.")
        raw_mappings = payload.get("mappings")
        if not isinstance(raw_mappings, dict):
            raise PseudonymStoreError("Table de correspondances invalide pour ce dossier.")

        mappings: dict[str, dict[str, str]] = {}
        seen_pseudonyms: set[str] = set()
        for entity_type, bucket in raw_mappings.items():
            if entity_type not in SUPPORTED_ENTITY_TYPES or not isinstance(bucket, dict):
                raise PseudonymStoreError("Table de correspondances invalide pour ce dossier.")
            validated: dict[str, str] = {}
            for original, pseudonym in bucket.items():
                if (
                    not isinstance(original, str)
                    or not isinstance(pseudonym, str)
                    or not original.strip()
                    or not pseudonym.strip()
                    or _index_from_pseudonym(entity_type, pseudonym) == 0
                ):
                    raise PseudonymStoreError("Table de correspondances invalide pour ce dossier.")
                if pseudonym in seen_pseudonyms:
                    raise PseudonymStoreError(
                        "Pseudonyme dupliqué dans la table de correspondances."
                    )
                seen_pseudonyms.add(pseudonym)
                validated[original] = pseudonym
            mappings[entity_type] = validated
        return mappings

    def _encrypt_state(self, mappings: dict[str, dict[str, str]]) -> bytes:
        """Chiffre un état JSON complet sans modifier le jeton canonique."""
        payload = {
            "version": self._VERSION,
            "case_id": self.case_id,
            "mappings": mappings,
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self._fernet.encrypt(serialized.encode("utf-8"))

    def _write_state(self, mappings: dict[str, dict[str, str]]) -> None:
        """Chiffre l'état JSON complet et en fait le jeton canonique."""
        self._token = self._encrypt_state(mappings)


PseudonymResolver = Callable[[str, str], str]


class _PseudonymizingOperator(Operator):
    """Opérateur Presidio qui délègue chaque remplacement à un résolveur dédié."""

    def operate(self, text: str, params: dict[str, Any] | None = None) -> str:
        resolver = (params or {}).get("resolver")
        if not callable(resolver):
            raise PseudonymStoreError("Résolveur de pseudonymisation absent.")
        return resolver((params or {}).get("entity_type"), text)

    def validate(self, params: dict[str, Any] | None = None) -> None:
        if not callable((params or {}).get("resolver")):
            raise PseudonymStoreError("Résolveur de pseudonymisation absent.")

    def operator_name(self) -> str:
        return "pseudonymize"

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize


def _build_recognizers() -> list[PatternRecognizer]:
    """Crée les quatre reconnaisseurs de motifs Presidio déterministes."""
    return [
        PatternRecognizer(
            supported_entity="IP_ADDRESS",
            name="iryx_ip_address",
            patterns=[Pattern("ipv4_private_or_public", IP_ADDRESS_PATTERN, 1.0)],
        ),
        PatternRecognizer(
            supported_entity="HOSTNAME",
            name="iryx_hostname",
            patterns=[Pattern("netbios_hostname", HOSTNAME_PATTERN, 0.9)],
        ),
        PatternRecognizer(
            supported_entity="USER_ACCOUNT",
            name="iryx_user_account",
            patterns=[Pattern("technical_account", USER_ACCOUNT_PATTERN, 0.85)],
        ),
        PatternRecognizer(
            supported_entity="EMAIL_ADDRESS",
            name="iryx_email_address",
            patterns=[Pattern("email_address", EMAIL_ADDRESS_PATTERN, 1.0)],
        ),
    ]


def _build_analyzer() -> AnalyzerEngine:
    """Construit un analyseur hors ligne avec le moteur NLP ``no_op`` de Presidio."""
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "no_op",
            "models": [{"lang_code": "en", "model_name": "noop"}],
        }
    ).create_engine()
    registry = RecognizerRegistry(recognizers=_build_recognizers(), supported_languages=["en"])
    return AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["en"])


def _select_non_overlapping(results: list[Any]) -> list[Any]:
    """Résout les détections selon le score, la longueur puis la position."""
    ranked = sorted(
        results,
        key=lambda result: (-result.score, -(result.end - result.start), result.start, result.end),
    )
    selected: list[Any] = []
    for result in ranked:
        if any(result.start < kept.end and kept.start < result.end for kept in selected):
            continue
        selected.append(result)
    selected.sort(key=lambda result: (result.start, result.end))
    return selected


class DeterministicPseudonymizer:
    """Service de pseudonymisation déterministe et propre au dossier (FR25 / D-19)."""

    def __init__(self, secret_key: str | None = None) -> None:
        resolved_key = secret_key if secret_key is not None else get_settings().secret_key
        if not resolved_key:
            raise ValueError("La clé secrète de pseudonymisation ne peut pas être vide.")
        self._secret_key = resolved_key
        self._stores: dict[str, CasePseudonymStore] = {}
        self._analyzer = _build_analyzer()
        self._anonymizer = AnonymizerEngine()
        if _HAS_ADD_ANONYMIZER:
            self._anonymizer.add_anonymizer(_PseudonymizingOperator)

    def get_store(self, case_id: str | uuid.UUID) -> CasePseudonymStore:
        """Retourne (ou crée paresseusement) le magasin chiffré dédié à un dossier."""
        normalized = _normalize_case_id(case_id)
        if normalized not in self._stores:
            self._stores[normalized] = CasePseudonymStore(normalized, secret_key=self._secret_key)
        return self._stores[normalized]

    def register_store(self, store: CasePseudonymStore) -> None:
        """Enregistre un magasin déjà restauré pour son dossier."""
        if not isinstance(store, CasePseudonymStore):
            raise TypeError("store doit être une instance de CasePseudonymStore.")
        expected_key = CasePseudonymStore.derive_key(store.case_id, self._secret_key)
        if store._key != expected_key:
            raise PseudonymStoreError("La table fournie utilise une clé secrète différente.")
        self._stores[store.case_id] = store

    def load_store(self, case_id: str | uuid.UUID, token: str | bytes) -> CasePseudonymStore:
        """Restaure un magasin depuis un jeton chiffré et l'enregistre."""
        store = CasePseudonymStore(case_id, secret_key=self._secret_key, token=token)
        self.register_store(store)
        return store

    def export_token(self, case_id: str | uuid.UUID) -> str:
        """Exporte le jeton chiffré de la table de correspondances d'un dossier."""
        return self.get_store(case_id).export_token()

    def pseudonymize(
        self,
        request: PseudonymizeRequest | str,
        case_id: str | uuid.UUID | None = None,
        entities: list[str] | None = None,
        *,
        store: CasePseudonymStore | None = None,
    ) -> PseudonymizeResult:
        """Pseudonymise un texte dans un dossier et retourne des métadonnées typées.

        Accepte une ``PseudonymizeRequest`` ou un texte brut avec un ``case_id`` explicite.
        """
        if isinstance(request, PseudonymizeRequest):
            normalized_case_id = request.case_id
            text = request.text
            requested_entities = request.entities
        else:
            if case_id is None:
                raise ValueError("case_id est requis lorsque le texte est fourni directement.")
            normalized_case_id = _normalize_case_id(case_id)
            text = request
            requested_entities = (
                [entity.strip().upper() for entity in entities if entity.strip()]
                if entities
                else None
            )

        if requested_entities:
            invalid = [
                entity for entity in requested_entities if entity not in SUPPORTED_ENTITY_TYPES
            ]
            if invalid:
                raise ValueError(
                    "Types d'entités non pris en charge : " + ", ".join(sorted(invalid))
                )

        if not text.strip():
            return PseudonymizeResult(
                case_id=normalized_case_id,
                pseudonymized_text="",
                entities=[],
                entity_count=0,
                has_entities=False,
            )

        active_store = store or self.get_store(normalized_case_id)
        if active_store.case_id != normalized_case_id:
            raise PseudonymStoreError("La table fournie appartient à un autre dossier.")
        self.register_store(active_store)

        allowed = set(requested_entities) if requested_entities else set(SUPPORTED_ENTITY_TYPES)
        analyzed = self._analyzer.analyze(
            text=text,
            language="en",
            entities=[entity for entity in SUPPORTED_ENTITY_TYPES if entity in allowed],
        )
        candidates = [result for result in analyzed if result.entity_type in SUPPORTED_ENTITY_TYPES]
        selected = _select_non_overlapping(candidates)

        # Attribue les pseudonymes par position croissante avant d'invoquer
        # l'anonymiseur Presidio, qui opère de la fin du texte vers le début.
        assigned: dict[tuple[str, str], str] = {}
        entity_infos: list[DetectedEntityInfo] = []
        for result in selected:
            original = text[result.start : result.end]
            key = (result.entity_type, original)
            pseudonym = assigned.get(key)
            if pseudonym is None:
                pseudonym = active_store.get_pseudonym(result.entity_type, original)
                assigned[key] = pseudonym
            entity_infos.append(
                DetectedEntityInfo(
                    entity_type=result.entity_type,
                    start=result.start,
                    end=result.end,
                    score=result.score,
                    pseudonym=pseudonym,
                )
            )

        def resolver(entity_type: str, original: str) -> str:
            key = (entity_type, original)
            if key not in assigned:
                assigned[key] = active_store.get_pseudonym(entity_type, original)
            return assigned[key]

        operators = {
            entity_type: OperatorConfig("pseudonymize", {"resolver": resolver})
            for entity_type in SUPPORTED_ENTITY_TYPES
        }
        anonymize_kwargs: dict[str, Any] = {
            "text": text,
            "analyzer_results": selected,
            "operators": operators,
        }
        if _ANONYMIZE_SUPPORTS_MERGE_SPACES:
            anonymize_kwargs["merge_entities_with_spaces"] = False
        anonymized = self._anonymizer.anonymize(**anonymize_kwargs)

        return PseudonymizeResult(
            case_id=normalized_case_id,
            pseudonymized_text=anonymized.text,
            entities=entity_infos,
        )

    def depseudonymize(
        self,
        case_id: str | uuid.UUID,
        text: str,
        *,
        store: CasePseudonymStore | None = None,
    ) -> str:
        """Restaure localement un texte pseudonymisé via la table chiffrée du dossier."""
        normalized_case_id = _normalize_case_id(case_id)
        active_store = store or self.get_store(normalized_case_id)
        if active_store.case_id != normalized_case_id:
            raise PseudonymStoreError("La table fournie appartient à un autre dossier.")
        return active_store.depseudonymize(text)
