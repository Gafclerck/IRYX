"""Tests unitaires du module de pseudonymisation déterministe (Story 8.1).

Chaque scénario de la matrice I/O de la spec est couvert par un test dédié,
ainsi que les garanties de chiffrement, d'isolation et de non-divulgation.
"""

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet

from iryx.core.config import get_settings
from iryx.reporting import (
    CasePseudonymStore,
    DeterministicPseudonymizer,
    PseudonymizeRequest,
    PseudonymizeResult,
    PseudonymStoreError,
)

SECRET_KEY = os.environ["SECRET_KEY"]


@pytest.fixture
def pseudonymizer() -> DeterministicPseudonymizer:
    """Fournit un service isolé avec une clé secrète déterministe."""
    return DeterministicPseudonymizer(secret_key=SECRET_KEY)


class TestDeterministicPseudonymizer:
    """Détection, déterminisme et préservation de la structure du texte."""

    def test_nominal_detection_with_stable_pseudonyms(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """IP, hôte, compte et email sont détectés et remplacés par des pseudonymes convenus."""
        result = pseudonymizer.pseudonymize(
            PseudonymizeRequest(
                case_id="case_A",
                text=("IP 192.168.1.50 sur SRV-DC-01 par admin_ad; contact admin_ad@cert.gov"),
            )
        )

        assert isinstance(result, PseudonymizeResult)
        assert result.pseudonymized_text == (
            "IP IP_INTERNAL_1 sur HOST_SERVER_01 par USER_ACCOUNT_A; contact EMAIL_ADDRESS_1"
        )
        assert result.entity_count == 4
        assert result.has_entities is True
        assert {entity.entity_type for entity in result.entities} == {
            "IP_ADDRESS",
            "HOSTNAME",
            "USER_ACCOUNT",
            "EMAIL_ADDRESS",
        }

    def test_no_original_value_is_exposed_in_metadata(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Les métadonnées ne contiennent jamais la valeur sensible détectée."""
        result = pseudonymizer.pseudonymize("IP 192.168.1.50", case_id="case_A")

        assert result.entities[0].pseudonym == "IP_INTERNAL_1"
        assert "192.168.1.50" not in result.model_dump_json()
        assert result.entities[0].start == 3
        assert result.entities[0].end == 15
        assert 0.0 < result.entities[0].score <= 1.0

    def test_determinism_within_same_case(self, pseudonymizer: DeterministicPseudonymizer) -> None:
        """Une même valeur réutilisée dans un dossier reçoit toujours le même pseudonyme."""
        first = pseudonymizer.pseudonymize("IP 192.168.1.50", case_id="case_A")
        second = pseudonymizer.pseudonymize("Nouvelle ligne: 192.168.1.50", case_id="case_A")

        assert first.pseudonymized_text == "IP IP_INTERNAL_1"
        assert second.pseudonymized_text == "Nouvelle ligne: IP_INTERNAL_1"
        assert [entity.pseudonym for entity in second.entities] == ["IP_INTERNAL_1"]

    def test_distinct_values_get_distinct_pseudonyms(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Les compteurs augmentent dans l'ordre de position pour un même type."""
        result = pseudonymizer.pseudonymize(
            "10.0.0.1 puis 10.0.0.2 puis 10.0.0.1", case_id="case_A"
        )

        assert result.pseudonymized_text == "IP_INTERNAL_1 puis IP_INTERNAL_2 puis IP_INTERNAL_1"
        assert result.entity_count == 3

    def test_case_isolation(self, pseudonymizer: DeterministicPseudonymizer) -> None:
        """Deux dossiers distincts ne partagent ni clé ni jeton chiffré."""
        first = pseudonymizer.pseudonymize("IP 192.168.1.50", case_id="case_A")
        second = pseudonymizer.pseudonymize("IP 192.168.1.50", case_id="case_B")

        assert first.pseudonymized_text == second.pseudonymized_text == "IP IP_INTERNAL_1"
        assert CasePseudonymStore.derive_key("case_A", SECRET_KEY) != CasePseudonymStore.derive_key(
            "case_B", SECRET_KEY
        )
        assert pseudonymizer.export_token("case_A") != pseudonymizer.export_token("case_B")

    def test_store_from_another_case_is_rejected(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Une table chiffrée ne peut pas être réutilisée pour un autre dossier."""
        store = pseudonymizer.get_store("case_A")
        with pytest.raises(PseudonymStoreError):
            pseudonymizer.pseudonymize("IP 10.0.0.1", case_id="case_B", store=store)

    def test_text_without_sensitive_entities_is_unchanged(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Un texte neutre est retourné strictement identique."""
        text = "Analyse terminée : NFR-SEC-07 et ops normales."

        result = pseudonymizer.pseudonymize(text, case_id="case_A")

        assert result.pseudonymized_text == text
        assert result.entities == []
        assert result.entity_count == 0
        assert result.has_entities is False

    @pytest.mark.parametrize("text", ["", "   ", "\t\n"])
    def test_empty_or_whitespace_text_returns_empty_string(
        self, pseudonymizer: DeterministicPseudonymizer, text: str
    ) -> None:
        """Une chaîne vide ou blanche ne déclenche aucune analyse."""
        result = pseudonymizer.pseudonymize(text, case_id="case_A")

        assert result.pseudonymized_text == ""
        assert result.entities == []

    def test_entity_filter_limits_detection(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """La liste d'entités demandée restreint les détections actives."""
        result = pseudonymizer.pseudonymize(
            PseudonymizeRequest(
                case_id="case_A",
                text="IP 192.168.1.50 sur SRV-DC-01",
                entities=["ip_address"],
            )
        )

        assert result.pseudonymized_text == "IP IP_INTERNAL_1 sur SRV-DC-01"
        assert {entity.entity_type for entity in result.entities} == {"IP_ADDRESS"}

    def test_unsupported_entity_type_is_rejected(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Un type d'entité inconnu ne doit pas activer tous les détecteurs."""
        with pytest.raises(ValueError, match="IP_ADRESS"):
            pseudonymizer.pseudonymize(
                "IP 192.168.1.50 sur SRV-DC-01", case_id="case_A", entities=["IP_ADRESS"]
            )

    def test_raw_text_entity_filter_is_normalized(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """La signature texte brut normalise les types d'entités en majuscules."""
        result = pseudonymizer.pseudonymize(
            "IP 192.168.1.50 sur SRV-DC-01", case_id="case_A", entities=["ip_address"]
        )

        assert result.pseudonymized_text == "IP IP_INTERNAL_1 sur SRV-DC-01"
        assert {entity.entity_type for entity in result.entities} == {"IP_ADDRESS"}

    def test_pseudonymization_is_idempotent(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Un texte déjà pseudonymisé n'est pas pseudonymisé une seconde fois."""
        first = pseudonymizer.pseudonymize(
            "IP 192.168.1.50 sur SRV-DC-01 par admin_ad", case_id="case_A"
        )

        second = pseudonymizer.pseudonymize(
            first.pseudonymized_text, case_id="case_A"
        )

        assert second.pseudonymized_text == first.pseudonymized_text
        assert second.entities == []

    def test_depseudonymize_rejects_foreign_store(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """La dé-pseudonymisation refuse une table appartenant à un autre dossier."""
        store = pseudonymizer.get_store("case_A")
        pseudonymizer.pseudonymize("IP 192.168.1.50", case_id="case_A")

        with pytest.raises(PseudonymStoreError):
            pseudonymizer.depseudonymize("case_B", "IP IP_INTERNAL_1", store=store)

    def test_store_with_foreign_secret_is_rejected(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Une table chiffrée avec une autre clé secrète n'est pas acceptée."""
        foreign_store = CasePseudonymStore("case_A", secret_key="une-autre-cle-tres-longue")

        with pytest.raises(PseudonymStoreError):
            pseudonymizer.register_store(foreign_store)

    def test_cross_case_token_is_rejected(self) -> None:
        """Un jeton exporté d'un dossier ne peut pas être importé dans un autre."""
        first = DeterministicPseudonymizer(secret_key=SECRET_KEY)
        first.pseudonymize("IP 192.168.1.50", case_id="case_A")
        token = first.export_token("case_A")

        with pytest.raises(PseudonymStoreError):
            DeterministicPseudonymizer(secret_key=SECRET_KEY).load_store("case_B", token)

    def test_default_key_comes_from_settings(self) -> None:
        """Les constructeurs sans clé utilisent Settings.secret_key."""
        case_id = "case_A"
        expected_key = CasePseudonymStore.derive_key(case_id, get_settings().secret_key)

        service = DeterministicPseudonymizer()
        store = CasePseudonymStore(case_id)

        assert service._secret_key == get_settings().secret_key
        assert store._key == expected_key


class TestEncryptedCasePseudonymStore:
    """Chiffrement Fernet, restauration et dé-pseudonymisation contrôlée."""

    def test_token_contains_no_plaintext_value(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Le jeton exporté ne révèle aucune valeur d'origine."""
        pseudonymizer.pseudonymize("IP 192.168.1.50", case_id="case_A")
        token = pseudonymizer.export_token("case_A")

        assert "192.168.1.50" not in token
        assert token.startswith("gAAAAA")

    def test_restored_token_preserves_determinism(self) -> None:
        """Une table restaurée réutilise les pseudonymes déjà attribués."""
        first = DeterministicPseudonymizer(secret_key=SECRET_KEY)
        first.pseudonymize("IP 192.168.1.50", case_id="case_A")
        token = first.export_token("case_A")

        second = DeterministicPseudonymizer(secret_key=SECRET_KEY)
        second.load_store("case_A", token)
        result = second.pseudonymize(
            "192.168.1.50 puis 10.0.0.1", case_id="case_A"
        )

        assert result.pseudonymized_text == "IP_INTERNAL_1 puis IP_INTERNAL_2"
        assert [entity.pseudonym for entity in result.entities] == [
            "IP_INTERNAL_1",
            "IP_INTERNAL_2",
        ]

    def test_depseudonymization_restores_original_text(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """La dé-pseudonymisation locale restitue exactement le texte initial."""
        original = "Connexion depuis 192.168.1.50 sur SRV-DC-01 par admin_ad"
        pseudonymized = pseudonymizer.pseudonymize(original, case_id="case_A")

        restored = pseudonymizer.depseudonymize("case_A", pseudonymized.pseudonymized_text)

        assert restored == original

    def test_corrupted_token_raises_controlled_error(
        self, pseudonymizer: DeterministicPseudonymizer
    ) -> None:
        """Un jeton altéré lève une exception contrôlée sans trace de la valeur."""
        pseudonymizer.pseudonymize("IP 192.168.1.50", case_id="case_A")
        token = pseudonymizer.export_token("case_A")
        corrupted = ("x" if token[0] != "x" else "y") + token[1:]

        with pytest.raises(PseudonymStoreError) as excinfo:
            DeterministicPseudonymizer(secret_key=SECRET_KEY).load_store("case_A", corrupted)

        assert "192.168.1.50" not in str(excinfo.value)
        assert SECRET_KEY not in str(excinfo.value)

    def test_wrong_secret_key_is_rejected(self) -> None:
        """Une clé différente ne peut pas déchiffrer la table d'un dossier."""
        first = DeterministicPseudonymizer(secret_key=SECRET_KEY)
        first.pseudonymize("IP 192.168.1.50", case_id="case_A")
        token = first.export_token("case_A")

        cle_invalide = "une-autre-cle-tres-longue"
        with pytest.raises(PseudonymStoreError) as excinfo:
            DeterministicPseudonymizer(secret_key=cle_invalide).load_store("case_A", token)

        assert "192.168.1.50" not in str(excinfo.value)
        assert SECRET_KEY not in str(excinfo.value)
        assert cle_invalide not in str(excinfo.value)

    def test_uuid_case_id_is_normalized(self, pseudonymizer: DeterministicPseudonymizer) -> None:
        """Un UUID est accepté comme identifiant de dossier stable."""
        case_id = uuid.uuid4()

        result = pseudonymizer.pseudonymize("IP 10.0.0.1", case_id=case_id)

        assert result.case_id == str(case_id)

    def test_semantically_invalid_token_is_rejected(self) -> None:
        """Un jeton chiffré valide mais sémantiquement incohérent est refusé."""
        case_id = "case_A"
        key = CasePseudonymStore.derive_key(case_id, SECRET_KEY)
        payload = {
            "version": 1,
            "case_id": case_id,
            "mappings": {
                "IP_ADDRESS": {
                    "192.168.1.50": "IP_INTERNAL_1",
                    "10.0.0.1": "IP_INTERNAL_1",
                }
            },
        }
        token = Fernet(key).encrypt(json.dumps(payload).encode("utf-8"))

        with pytest.raises(PseudonymStoreError, match="dupliqué"):
            CasePseudonymStore(case_id, secret_key=SECRET_KEY, token=token)

    def test_concurrent_pseudonymizations_do_not_lose_mappings(self) -> None:
        """Des attributions simultanées conservent toutes les correspondances du dossier."""
        case_id = "case-concurrent"
        store = CasePseudonymStore(case_id, secret_key=SECRET_KEY)
        values = [f"10.0.0.{index}" for index in range(1, 9)]

        with ThreadPoolExecutor(max_workers=len(values)) as executor:
            assigned = list(
                executor.map(lambda value: store.get_pseudonym("IP_ADDRESS", value), values)
            )

        assert len(set(assigned)) == len(values)
        restored = CasePseudonymStore(case_id, secret_key=SECRET_KEY, token=store.export_token())
        for value, pseudonym in zip(values, assigned, strict=True):
            assert restored.get_pseudonym("IP_ADDRESS", value) == pseudonym
