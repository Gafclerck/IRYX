# Epic 6 Context: E6 - Findings et revue humaine (H2)

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Permettre à l'agent Analyst de formuler des constats d'enquête structurés (`Finding`), faire certifier chaque constat par le composant déterministe `Verifier` (qui valide en SQL relationnel pur sans aucun LLM l'existence réelle en base des observations et exécutions d'outils référencées), suspendre l'enquête à la porte de contrôle humain H2, et offrir à l'analyste l'API complète pour valider, rectifier ou rejeter chaque constat avant son intégration dans la timeline et le rapport.

## Stories

- Story 6.1: Modèle `Finding`, schémas Pydantic et migration Alembic
- Story 6.2: Agent `Analyst` et formulation structurée des constats d'enquête (FR22)
- Story 6.3: Composant `Verifier` déterministe formel sans appel LLM (FR23, NFR-REL-01)
- Story 6.4: Porte Humaine H2 (Validation des findings) et API de revue (FR19)

## Requirements & Constraints

- **Modèle Finding et Intégrité Relationnelle (Invariant 1, FR22)** : Chaque constat technique comporte un identifiant unique (UUID), un rattachement de dossier (`case_id`), un titre, une sévérité (`low`, `medium`, `high`, `critical`), un niveau de confiance (`low`, `medium`, `high`), un type (`fact`, `inference`, `hypothesis`), un statut (`proposed`, `validated`, `rejected`), des listes de références d'observations (`observation_refs`) et d'exécutions d'outils (`tool_execution_refs`), ainsi que l'identifiant de création (`created_by`) et l'horodatage UTC (`created_at`).
- **Garantie Anti-Hallucination Déterministe (FR23, NFR-REL-01)** : Le composant `Verifier` doit valider à 100% en SQL relationnel que chaque UUID référencé dans `observation_refs` et `tool_execution_refs` existe réellement dans la base et appartient strictement au même `case_id`. Tout constat comportant une référence fictive, manquante ou issue d'un autre dossier doit être immédiatement invalidé avec le code `HALLUCINATED_REFERENCE_DETECTED`. Aucun modèle LLM ne doit être interrogé par le Verifier.
- **Porte de Contrôle Humain H2 (FR19)** : La session d'enquête se met en pause à l'état `waiting_h2`. L'analyste SOC/DFIR peut consulter la liste paginée des findings, ajuster la sévérité et la confiance, valider (`validate`) ou rejeter (`reject`) chaque constat. Seuls les constats validés sont éligibles pour la timeline chronologique et les rapports finaux. L'accès requiert des privilèges d'écriture sur le dossier (`verify_case_access`).
- **Sécurité et Isolation Multi-Tenant (NFR-SEC-06, D-05, D-06)** : Toute manipulation ou consultation de constats impose la vérification d'appartenance de l'utilisateur à l'organisation détentrice du dossier.

## Technical Decisions

- **D-04 (Schémas Pydantic v2)** : Schémas `FindingCreate`, `FindingUpdate`, `FindingReview`, `FindingOut` avec validation stricte des énumérations (`severity`, `confidence`, `finding_type`, `status`).
- **D-05 / D-06 (PostgreSQL & SQLAlchemy 2.x)** : Table relationnelle `findings` avec colonnes `ARRAY(UUID)` pour `observation_refs` et `tool_execution_refs`, clés étrangères vers `cases.id` et `users.id`, index sur `case_id` et `status`.
- **D-07 (Migrations Alembic)** : Migration Alembic dédiée pour créer la table `findings` et ses types énumérés / index associés.
- **D-09 (LangGraph Orchestrator)** : Transition d'état `analyst` -> `verifier` -> `gate_h2` avec interruption humaine (`interrupt()` ou mise en pause d'état).
- **D-10 / D-11 (Client LLM unifié OpenAI)** : Utilisé par l'agent Analyst avec structured outputs / function calling pour garantir le format JSON du finding.
- **D-24 (Polling REST)** : Suivi et revue via API REST standard `/api/v1/cases/{case_id}/findings`.

## Cross-Story Dependencies

- **Story 6.1** fournit la fondation de données (table `findings`, modèle SQLAlchemy, schémas Pydantic) requise par les stories 6.2, 6.3 et 6.4.
- **Story 6.2** (Agent Analyst) instancie et sauvegarde les constats avec `status: proposed`.
- **Story 6.3** (Verifier déterministe) certifie les références avant que les constats ne soient présentés à l'humain.
- **Story 6.4** (Porte H2) permet la validation par l'analyste, qui met à jour les statuts en `validated` ou `rejected`.
