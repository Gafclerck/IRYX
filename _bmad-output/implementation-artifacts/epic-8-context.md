# Epic 8 Context: E8 - Rapports et journal d'audit

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Implémenter la pseudonymisation déterministe des entités sensibles via Microsoft Presidio (D-19), gérer la porte de contrôle humain H3 (autorisation explicite avant tout transfert vers un LLM externe), orchestrer la rédaction et le scellement cryptographique SHA-256 des rapports d'incident finaux (formats Markdown et JSON), et verrouiller la traçabilité complète du système via un journal d'audit immuable en ajout seul (`AuditEvent`) protégé par déclencheur SQL (Invariant 3).

## Stories

- Story 8.1: Module de pseudonymisation déterministe Microsoft Presidio (FR25, D-19, NFR-SEC-07)
- Story 8.2: Porte Humaine H3 (Autorisation d'envoi LLM externe) et prévisualisation sécurisée (FR20)
- Story 8.3: Modèle `Report`, agent `Rapporteur`, génération et scellement SHA-256 du rapport (FR26)
- Story 8.4: Endpoints de consultation et téléchargement des rapports scellés
- Story 8.5: Service d'audit immuable en ajout seul `AuditEvent` et déclencheur d'intégrité (FR27, NFR-SEC-03)

## Requirements & Constraints

- **Pseudonymisation déterministe (FR25, NFR-SEC-07, D-19)** : Remplacement déterministe et stable par dossier des entités sensibles (adresses IP, noms d'hôtes, comptes utilisateurs, emails) par des pseudonymes structurés (`IP_INTERNAL_1`, `HOST_SERVER_01`, `USER_ACCOUNT_A`) via `presidio-analyzer` et `presidio-anonymizer` avec règles et reconnaisseurs personnalisés pour les identifiants techniques.
- **Porte de contrôle humain H3 (FR20)** : Suspension obligatoire du graphe LangGraph à l'état `waiting_h3` avant toute expédition de synthèse à un LLM externe. Consultation d'une prévisualisation anonymisée (`anonymized-preview`) et arbitrage explicite par l'analyste (approbation ou refus / mode hors-ligne).
- **Rapport d'incident scellé (FR26, NFR-SEC-01)** : Génération par l'agent Rapporteur aux formats Markdown et JSON à partir des Findings validés (porte H2) et observations certifiées. Calcul et enregistrement de l'empreinte SHA-256 dans l'entité `Report`.
- **Téléchargement sécurisé (FR26)** : Exposition d'endpoints de consultation et téléchargement des rapports avec en-tête standardisé `X-Report-SHA256` et types MIME conformes (`text/markdown`, `application/json`).
- **Journal d'audit immuable en ajout seul (FR27, NFR-SEC-03, Invariant 3)** : Enregistrement synchrone dans `audit_events` de toutes les actions sensibles avec calcul de hash SHA-256 du payload (`payload_hash`), détails contextuels JSONB (exempts de secrets). Déclencheur SQL PostgreSQL (`trigger`) rejetant catégoriquement toute opération `UPDATE` ou `DELETE` avec levée de l'erreur `CANNOT_MODIFY_AUDIT_LOG`.
- **Cloisonnement et contrôle d'accès strict (NFR-SEC-05, FR4)** : Tous les endpoints de reporting et de consultation de piste d'audit sont strictement isolés par organisation et dossier via `verify_case_access`.

## Technical Decisions

- **D-04 (Pydantic v2)** : Schémas de validation pour les requêtes H3, les entités de rapports (`ReportOut`), la piste d'audit (`AuditEventOut`) et les structures de pseudonymisation.
- **D-05 / D-06 / D-07 (PostgreSQL 16, SQLAlchemy 2.x, Alembic)** : Modèles relationnels `Report` et `AuditEvent` avec migration Alembic et fonction/trigger PostgreSQL d'interdiction formelle des modifications / suppressions.
- **D-09 / D-10 (LangGraph & Client LLM unifié)** : Nœuds de graphe pour la porte H3 et l'agent Rapporteur, utilisant le client LLM paramétré avec réessais Tenacity.
- **D-14 (Hashlib SHA-256)** : Calcul de l'empreinte cryptographique des rapports générés et du payload des événements d'audit.
- **D-19 (Microsoft Presidio)** : Intégration de `presidio-analyzer` et `presidio-anonymizer` (>=2.2.366, version plancher validée) avec recognizers regex adaptés aux artefacts forensiques.
- **D-23 (Logging structuré)** : Traçabilité des actions sans secrets (zéro token, clé d'API ou mot de passe dans les logs et événements d'audit).

## Cross-Story Dependencies

- **Story 8.1** fournit le socle de pseudonymisation déterministe via Microsoft Presidio, prérequis technique immédiat pour la prévisualisation H3.
- **Story 8.2** implémente la porte humaine H3 et s'appuie sur le service de pseudonymisation de Story 8.1.
- **Story 8.3** introduit le modèle `Report` et l'agent `Rapporteur` qui intervient après franchissement de la porte H3.
- **Story 8.4** expose l'accès API aux rapports scellés générés par Story 8.3.
- **Story 8.5** formalise la persistance `AuditEvent` avec le trigger SQL PostgreSQL d'immutabilité et le service d'audit synchrone mobilisé sur l'ensemble du système.
