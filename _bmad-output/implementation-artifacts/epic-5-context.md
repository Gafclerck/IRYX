# Epic 5 Context: Orchestrateur, agents et gates

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Déployer le graphe d'états LangGraph pilotant la session d'enquête numérique (`InvestigationRun`, `Phase`), intégrer le client LLM unifié basé sur le SDK officiel `openai` avec réessais automatiques `tenacity` et balisage passif `<forensic_data>`, implémenter l'agent `Planner` générant un plan d'actions borné (max 10 étapes), interrompre obligatoirement le graphe à la porte de validation humaine H1 pour arbitrage de l'analyste, permettre à l'agent procédural `Executor` de déclencher les outils approuvés via la Gateway forensique, et assurer la persistance transactionnelle d'état et la reprise sur incident via le checkpointer PostgreSQL.

## Stories

- Story 5.1: Client LLM unifié OpenAI avec réessais Tenacity et prompts système sécurisés (D-10, D-11, NFR-SEC-06)
- Story 5.2: Modèles `InvestigationRun` et `Phase`, schémas et initialisation du graphe LangGraph (FR16)
- Story 5.3: Agent `Planner` et proposition de plan d'investigation borné (FR17, NFR-PERF-05)
- Story 5.4: Porte Humaine H1 (Validation du plan d'action) et API d'arbitrage (FR18)
- Story 5.5: Agent `Executor` procédural et dispatch sécurisé vers la Gateway forensique (FR20)
- Story 5.6: Persistance transactionnelle d'état, checkpointer PostgreSQL et reprise sur incident (FR21, NFR-PERF-04)

## Requirements & Constraints

- **Client LLM unifié et résilient** : Utilisation exclusive du SDK officiel `openai` (>=1.50.0). Paramétrage par rôle (`base_url`, `model`). Encapsulation avec `tenacity` (jusqu'à 3 tentatives avec backoff exponentiel 1s, 2s, 4s en cas de 503, 429 ou timeout de 60s). Levée d'une exception typée `LLMServiceUnavailableException` en cas d'échec persistant.
- **Immunisation contre l'injection de prompts (NFR-SEC-06)** : Encapsulation systématique des données de preuves brutes dans des balises passives `<forensic_data>` avec instruction système formelle interdisant au LLM d'exécuter des consignes contenues dans les preuves.
- **Sécurité des secrets et des logs** : Les clés d'API LLM sont chargées via des variables d'environnement dans les paramètres Pydantic (`OPENAI_API_BASE`, `OPENAI_API_KEY`). Aucune clé d'API ne doit apparaître dans les logs ou les messages d'erreur.
- **Orchestration LangGraph bornée** : Graphe d'états orchestrant rigoureusement les phases : Triage -> Planner -> Gate H1 -> Executor -> Analyst -> Verifier -> Gate H2 -> Pseudonymisation -> Gate H3 -> Reporting. Boucle bornée à 5 itérations maximum pour éviter tout emballement.
- **Plan d'actions borné (Planner - NFR-PERF-05)** : Le plan proposé par l'agent Planner contient un maximum strict de 10 étapes validées contre un schéma Pydantic `InvestigationPlan`. Les outils proposés doivent obligatoirement être présents dans le registre `ToolRegistry`.
- **Porte de validation humaine H1 obligatoire** : Interruption impérative du graphe à la porte H1. L'agent `Executor` ne peut exécuter aucun outil sans accord explicite (`approve`) de l'analyste via l'API REST.
- **Agent Executor déterministe** : Zéro appel LLM dans l'Executor. Exécution séquentielle et contrôlée via `ToolRegistry.execute_tool` avec journalisation complète dans `tool_executions`.
- **Persistance et reprise sur incident (Checkpointer)** : Sauvegarde de l'état du graphe dans PostgreSQL 16 permettant la reprise d'une session interrompue sans perte de données. Une seule session d'investigation active par dossier à la fois (HTTP 409 `INVESTIGATION_ALREADY_RUNNING`).

## Technical Decisions

- **D-04** : Validation des schémas Pydantic v2 pour les configurations LLM, le plan d'investigation (`InvestigationPlan`) et les transitions de phase.
- **D-05 & D-06** : Modèles relationnels PostgreSQL 16 avec SQLAlchemy 2.x (`InvestigationRun`, `Phase`).
- **D-07** : Migration Alembic dédiée pour les tables de session d'enquête et de phases.
- **D-09** : LangGraph (>=0.2.20) pour l'orchestration du graphe d'états et le contrôle d'interruption.
- **D-10** : SDK officiel `openai` (>=1.50.0) comme client unique compatible OpenAI (Groq / RodiumAi en dev, Gemma auto-hébergé en prod).
- **D-11** : `tenacity` (>=9.0.0) pour la résilience réseau avec backoff exponentiel.
- **D-24** : Troncature et protection contextuelle lors de l'alimentation des agents.

## Cross-Story Dependencies

- E5 dépend de E1 (socle, auth), E2 (dossiers, RBAC), E3 (preuves scellées) et E4 (registre d'outils et observations).
- Story 5.1 établit le client LLM unifié et sécurisé servant de brique commune à tous les agents conversationnels (Planner, Analyst, Rapporteur).
- Story 5.2 crée les tables de sessions (`InvestigationRun`, `Phase`) et structure le graphe LangGraph.
- Story 5.3 implémente l'agent `Planner` s'appuyant sur le client LLM (5.1) et les preuves (E3).
- Story 5.4 ajoute la porte d'arbitrage H1 (`paused` / `waiting_h1`) et les endpoints d'approbation.
- Story 5.5 implémente l'agent procédural `Executor` déclenchant les outils approuvés via la Gateway (E4).
- Story 5.6 finalise la persistance transactionnelle du graphe et la reprise d'investigation sur incident.
