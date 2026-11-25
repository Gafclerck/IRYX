# Epic 7 Context: E7 - Corrélation et chronologie

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Construire le moteur de corrélation temporelle et générer la chronologie unifiée (timeline) de l'enquête exclusivement dérivée des faits techniques confirmés, garantissant le respect strict de l'Invariant 2 (interdiction formelle de forger ou modifier manuellement des entrées temporelles ex nihilo) et reliant les constats validés (Findings) aux événements sources.

## Stories

- Story 7.1: Service de reconstruction et de corrélation de la chronologie unifiée UTC (FR24)
- Story 7.2: API de consultation paginée et filtrage de la Timeline d'enquête (NFR-PERF-07)
- Story 7.3: Moteur de corrélation multi-sources et mise en correspondance des Findings

## Requirements & Constraints

- **Reconstruction déterministe de la Timeline (FR24)** : Agréger toutes les entités `Observation` associées à un dossier (`case_id`), disposant d'un horodatage `timestamp_utc` non nul, et les ordonner par ordre chronologique strictement croissant en UTC.
- **Invariant 2 (Chronologie exclusivement dérivée des observations)** : Aucune entrée temporelle ne peut être forgée, insérée ou éditée manuellement dans la timeline d'un dossier. La chronologie est une vue/projection calculée pure à partir des observations techniques issues de preuves scellées.
- **Faits non horodatés** : Les observations sans horodatage extractible (`timestamp_utc` nul) doivent être isolées dans une catégorie dédiée (« Faits non horodatés ») afin de ne pas fausser l'ordre de la chronologie principale.
- **Contenu d'une entrée de Timeline** : Chaque point de la chronologie doit exposer l'horodatage UTC, l'identifiant de l'observation source (`observation_id`), le nom de l'outil générateur (`tool_name`), la référence de la preuve scellée d'origine (`evidence_id` / nom de la preuve), et le résumé du fait technique extrait du contenu normalisé (`normalized_content`).
- **Performance et volumétrie (NFR-PERF-07)** : Requêtes optimisées par index relationnel (`case_id`, `timestamp_utc`) pour supporter la pagination efficace (filtres par plage horaire, outil, preuve) sans saturer la mémoire.
- **Isolation Multi-Tenant et Sécurité (NFR-SEC-06, D-05, D-06)** : Toute interrogation de la chronologie est strictement cloisonnée par organisation et dossier, validée par `verify_case_access`.

## Technical Decisions

- **D-04 (Schémas Pydantic v2)** : Schémas de réponse de timeline et filtres typés (`TimelineEventOut`, `TimelineResponse`, etc.).
- **D-05 / D-06 (PostgreSQL & SQLAlchemy 2.x)** : Requêtes SQL optimisées avec tri `ORDER BY timestamp_utc ASC NULLS LAST` sur la table `observations`, jointures avec `evidences` et index composites.
- **D-09 / Orchestrateur & Analytics** : Implémentation du service dans le module `analytics` (ou composant dédié corrélateur `services.py`), fournissant la projection calculée pure de la timeline.
- **D-24 (API REST)** : Point d'accès paginé REST pour l'interrogation de la chronologie.

## Cross-Story Dependencies

- **Story 7.1** établit le service de base de corrélation et de reconstruction de la timeline UTC unifiée à partir des `Observation`.
- **Story 7.2** expose l'API de consultation paginée REST avec filtrage temporel (`start_time`, `end_time`) et par outil/source.
- **Story 7.3** enrichit la timeline avec la détection de corrélation multi-sources et la superposition des `Finding` validés lors de la porte H2.
