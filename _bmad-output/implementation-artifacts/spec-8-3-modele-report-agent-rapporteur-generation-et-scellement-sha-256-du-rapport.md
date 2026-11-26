---
title: 'Story 8.3 : Modèle Report, agent Rapporteur, génération et scellement SHA-256 du rapport'
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_revision: '472bbc61396bb53b23ae67127cc09883d39b4237'
baseline_commit: '472bbc61396bb53b23ae67127cc09883d39b4237'
review_loop_iteration: 3  # figé depuis la boucle 3 : aucun bad_spec ni intent_gap depuis, uniquement des patchs
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
warnings: [oversized]
deferred:
  - summary: >-
      Préserver les identifiants de traçabilité du contexte Epic 8 lors de sa recompilation.
    evidence: |-
      La version régénérée remplace les libellés FR/NFR/D par une prose narrative et supprime les références explicites utilisées par les agents pour relier les stories aux exigences.
      Le correctif consiste à modifier un fichier de contexte agent ; il est donc différé.
    location: >-
      _bmad-output/implementation-artifacts/epic-8-context.md
    severity: medium
  - summary: >-
      Vérifier si le client LLM asynchrone peut être réutilisé après un bridge
      synchronisé depuis un event loop déjà actif.
    evidence: |-
      `_call_client_sync` exécute `asyncio.run(coro)` dans un thread séparé lorsqu'un
      event loop est déjà actif, alors que `UnifiedLLMClient` conserve un `AsyncOpenAI`
      instance créé à sa construction. Une affinité de boucle non démontrée pourrait
      faire échouer la rédaction externe. Un test avec client réel ou une preuve
      d'absence d'affinité trancherait; trouverait-on un échec, le correctif est une
      réforme du pont synchrone, hors périmètre d'un simple patch.
    location: >-
      backend/src/iryx/reporting/rapporteur_agent.py:207-215
    severity: medium (unverified)
  - summary: >-
        Éviter l'écrasement concurrent d'un jeton de pseudonymisation approuvé.
    evidence: |-
        Deux aperçus H3 concurrents peuvent tous deux lire l'absence de jeton puis écrire des jetons différents pour le même run. Le contrôle d'immutabilité séquentiel ne protège pas contre cette course. Le checkpointer ne fournit pas d'écriture conditionnelle atomique vérifiée dans le périmètre de la Story 8.3.
    location: >-
      backend/src/iryx/orchestrator/services.py:1026
    severity: low
  - summary: >-
        Éviter de maintenir le verrou de ligne du dossier pendant la rédaction externe.
    evidence: |-
        `_authorize(..., lock=True)`, `agent.generate_sync(...)` et `_allocate_version(...)` conservent la transaction et le verrou de ligne jusqu'à 60 secondes pendant l'appel LLM. Une restructuration transactionnelle (allocation puis libération avant rédaction, reverrouillage avant insertion) est hors périmètre de la Story 8.3.
    location: >-
      backend/src/iryx/reporting/services.py:279-289
    severity: medium
  - summary: >-
        Contrôler le format UUID de `reports.generation_id` par une contrainte CHECK.
    evidence: |-
        `generation_id` est `String(36)` sans contrainte de format dans la migration ni dans l'ORM ; une valeur non-UUID de 36 caractères pourrait être persistée puis rejetée à la lecture par `ReportOut`. Le contrat n'impose pas cette contrainte et l'ajout est différé.
    location: >-
      backend/migrations/versions/009_create_report_and_audit_tables.py
    severity: low
  - summary: >-
      Annuler coopérativement la rédaction externe après dépassement du délai.
    evidence: |-
      `future.cancel()` n'interrompt pas un appel LLM déjà lancé dans le worker. Une annulation coopérative demanderait un protocole dédié dans la rédaction externe, hors périmètre de la Story 8.3.
    location: >-
      backend/src/iryx/reporting/rapporteur_agent.py:651
    severity: low
  - summary: >-
      Démontrer une course réelle entre deux sessions sur (case_id, version, format).
    evidence: |-
      Le test séquentiel de conflit et le test de contrainte d'unicité couvrent le mécanisme de reprise ; un test threadé reste à ajouter si un scénario de concurrence réelle est exigé.
    location: >-
      backend/tests/unit/test_report_service.py
    severity: low
  - summary: >-
      Éviter la mutation du store de pseudonymisation avant la persistance du jeton.
    evidence: |-
      Le store injecté et le runtime context sont modifiés avant `_persist_pseudonymizer_token` ; une panne d'écriture du checkpointer laisserait un état divergente. Correctif transactionnel hors périmètre.
    location: >-
      backend/src/iryx/orchestrator/services.py:891
    severity: medium
  - summary: >-
      Nettoyer toutes les clés transitoires du runtime context entre deux requêtes.
    evidence: |-
      `_inject_runtime` ne retire que `llm_client` ; un `pseudonymizer`, `db`, `user_id`, `tool_registry` ou `tool_runner` périmé peut survivre dans le ContextVar et être relu par `get_anonymized_preview`.
    location: >-
      backend/src/iryx/orchestrator/services.py:990
    severity: medium
  - summary: >-
      Borner la taille du prompt externe et la pagination de `list_reports`.
    evidence: |-
      `_load_context` sérialise l'intégralité des constats, preuves, observations et événements de chronologie ; `list_reports` renvoie toutes les lignes correspondantes. Ces limites ne sont pas spécifiées par la Story 8.3.
    location: >-
      backend/src/iryx/reporting/rapporteur_agent.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** Le graphe d’investigation s’arrête à une phase `reporting` vide : malgré les portes H2/H3, aucun rapport d’incident n’est compilé, scellé ni persisté.

**Approach:** Introduire le modèle `Report`, un agent Rapporteur (LLM externe autorisé ou gabarit local déterministe), un compilateur Markdown/JSON calculant l’empreinte SHA-256, et brancher cette génération sur `reporting_node` sans affaiblir les garde-fous existants.

## Boundaries & Constraints

**Always:** La porte H3 reste infranchissable ; aucun appel LLM externe sans `h3_approved`. Un refus H3 ou `local_report_mode` force un gabarit local sans appel réseau. Seuls les findings `validated` alimentent le rapport. Le contenu persisté est exactement le contenu haché (`hashlib.sha256` sur les octets UTF-8), avec une empreinte par format. Un rapport `validated` est immuable : toute réécriture crée une génération distincte (`generation_id` nouveau, `version` incrémentée) et laisse l’ancienne intacte. Toutes les lectures sont cloisonnées par `case_id`. En échec, aucun rapport `validated` n’est créé et l’erreur est journalisée puis exposée avec le code `REPORT_GENERATION_FAILED`. La table `audit_events` est créée dans la même migration, mais son service et son trigger d’immutabilité restent à la Story 8.5.

**Never:** Réutiliser la révision `008` déjà occupée ; ignorer un verdict H3 ; modifier un rapport validé en place ; produire du PDF ; exposer les endpoints de téléchargement (Story 8.4) ; écrire dans la piste d’audit (Story 8.5) ; envoyer une donnée brute non pseudonymisée à un LLM externe.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| H3 approuvé et H2 validé | `h3_approved=True`, `db` et `case_id` disponibles | Deux lignes `Report` `validated` (`markdown`, `json`), `version=1`, empreintes SHA-256 correspondant au contenu stocké | Aucune |
| H3 refusé | `h3_rejected=True`, client LLM instrumenté | Rapport produit par le gabarit déterministe local ; `complete()` jamais appelé | Aucune |
| Constats non validés | Un finding `proposed` et un finding `validated` | Seul le finding `validated`, avec sa criticité, figure dans les deux formats | Aucune |
| Accès direct sans verdict | `reporting_node` appelé sans `h3_approved`/`h3_rejected` | `waiting_h3` / `paused`, aucune ligne `Report` créée | Aucune |
| Échec de génération | LLM indisponible ou compilation invalide | Aucune ligne `validated` | Log structuré + exception `REPORT_GENERATION_FAILED` (HTTP 500) |
| Régénération | Nouvelle génération demandée sur un rapport `validated` | Nouveaux `generation_id` et `version=2` ; anciennes lignes inchangées | Tentative de modification en place refusée par le service |
| Nœud isolé | State sans `db` ni `case_id` (tests unitaires existants) | Contrat actuel `reporting` / `running` conservé, aucune génération | Aucune |

</intent-contract>

## Code Map

- `backend/src/iryx/reporting/__init__.py:7-27` -- exporte aujourd’hui uniquement la pseudonymisation (Story 8.1) ; point d’entrée à étendre.
- `backend/src/iryx/reporting/pseudonymizer.py:434-577` -- `DeterministicPseudonymizer.pseudonymize()` à réutiliser avant tout appel LLM externe.
- `backend/src/iryx/reporting/schemas.py:104-163` -- schémas Pydantic v2 existants ; y ajouter les schémas `Report`.
- `backend/src/iryx/analytics/correlator.py:59-69` -- `get_validated_findings(case_id)` : source autorisée des findings, déjà filtrée sur `VALIDATED`.
- `backend/src/iryx/analytics/models.py:112-249` -- `Observation.timestamp_utc`, `Finding.severity`, `created_at` : provenance et criticité.
- `backend/src/iryx/evidence/models.py:38-91` -- `Evidence.sha256`, `original_name` : empreintes des preuves à citer.
- `backend/src/iryx/cases/models.py:38-121` -- `Case` : titre, description, statut : contexte du dossier.
- `backend/src/iryx/ai/client.py:49-307` -- `UnifiedLLMClient.for_role()` / `complete()` ; `LLMRole.RAPPORTEUR` existe dans `ai/schemas.py:9-15`.
- `backend/src/iryx/ai/prompts.py:25-75` -- `build_system_prompt()` et garde-fou anti-injection à réutiliser.
- `backend/src/iryx/orchestrator/graph.py:506-528` -- `reporting_node` : garde H3 actuelle à préserver, point de branchement de la génération.
- `backend/src/iryx/orchestrator/state.py:40-62` -- `report: dict | None` : support de sortie déjà présent, aucun nouveau champ d’état requis.
- `backend/src/iryx/core/exceptions.py:19-31,479-491` -- motif `IryxException` / code HTTP à suivre pour `REPORT_GENERATION_FAILED`.
- `backend/migrations/versions/008_create_observations_case_id_timestamp_utc_index.py:14-17` -- head actuelle ; la nouvelle migration doit être `009`, `down_revision="008"`.
- `backend/migrations/env.py:13-31` -- imports de modèles pour `target_metadata` ; à étendre pour que les nouvelles tables soient visibles.
- `backend/tests/unit/test_finding_migration.py:37`, `test_investigation_migration.py:37`, `test_timeline_migration.py:39` -- assertions figées sur `get_heads() == ["008"]` à mettre à jour.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/reporting/models.py` -- créer l’ORM `Report` : `id`, `case_id` (FK CASCADE), `format` (`markdown|json`), `content` (texte non nul), `sha256` (`String(64)`, indexé), `status` (`draft|validated|exported`), `generation_id`, `version`, `created_at` UTC, contraintes de vérification et index ; exprimer les `CHECK` hexadécimaux de façon portable (expression SQLAlchemy compilable en regex PostgreSQL et en `GLOB` SQLite), jamais une syntaxe `GLOB` figée dans les métadonnées -- fournit une persistance scellée sans dérive entre `create_all`/autogenerate et la migration.
- [x] `backend/src/iryx/audit/models.py` -- créer l’ORM minimal `AuditEvent` correspondant à la table créée par la migration, sans service ni trigger ; `CHECK` hexadécimal portable sur `payload_sha256` et FKs `RESTRICT` -- garde les métadonnées alignées et prépare la Story 8.5.
- [x] `backend/src/iryx/core/exceptions.py` -- ajouter `ReportGenerationFailedException` avec `code="REPORT_GENERATION_FAILED"` et statut 500 -- erreur consignable et exposable dans l’enveloppe JSON standard.
- [x] `backend/src/iryx/reporting/schemas.py` -- ajouter `ReportFormat`, `ReportStatus`, `ReportSection`, `ReportContent` et `ReportOut` (Pydantic v2) -- contrat typé des sections et des métadonnées exposées.
- [x] `backend/src/iryx/reporting/compiler.py` -- rendre la structure canonique en Markdown lisible et en JSON déterministe, puis calculer `hashlib.sha256` sur les octets exacts stockés -- garantit une empreinte reproductible et vérifiable.
- [x] `backend/src/iryx/reporting/rapporteur_agent.py` -- créer `RapporteurAgent` avec un paramètre explicite `h3_approved: bool = False` : le mode externe n'est accessible que si `h3_approved is True`, sinon le gabarit local est utilisé sans aucun appel réseau ; le client obtenu via `for_role(LLMRole.RAPPORTEUR)` doit être vérifié comme configuré pour ce rôle ; pseudonymiser avec le pseudonymiseur partagé avant tout appel, sans retomber silencieusement sur une instance neuve ; parser le JSON de façon tolérante en exigeant les huit sections ; reconstruire `constats_valides` depuis `facts` **et** rejeter toute mention, dans n'importe quelle section, d'un titre qui n'est pas exactement un constat validé fourni dans `facts` (y compris un titre inventé absent de la liste des constats non validés transmis par le service) ; considérer comme mention détectable toute clé structurée de titre, toute ligne précédée d'une criticité entre crochets, toute phrase introduite par « constat » ou « finding » et toute correspondance exacte avec un titre non validé transmis, chaque extrait détecté devant correspondre exactement à un constat validé ou à sa forme pseudonymisée -- produit une synthèse qui ne peut pas inventer ni divulguer un constat non validé.
- [x] `backend/src/iryx/reporting/services.py` -- orchestrer contexte dossier, preuves, observations, chronologie et findings validés ; transmettre à l'agent les titres des constats non validés et vérifier qu'aucun titre hors ensemble validé n'est persisté ; exiger `user_id` pour tout appel non interne et refuser l'accès avant toute lecture ; allouer `version` sous verrou de ligne du dossier avec une contrainte d'unicité `(case_id, version, format)` ; générer `generation_id` exclusivement en interne (aucune valeur appelant acceptée, y compris en cas de conflit) ; persister les deux formats dans une seule transaction ; recalculer toujours `sha256` depuis `content` sans accepter de valeur appelant ; valider `status` via `ReportStatus` ; `update_report` ne peut modifier qu'une ligne `draft` et ne peut jamais promouvoir une ligne en `validated` : la promotion vers `validated` passe obligatoirement par `generate_report` ; journaliser sans `exc_info` ni contenu de rapport ; exiger un pseudonymiseur injecté dès que `h3_approved is True`, sans instance neuve ; refuser tout verdict H3 négatif explicite ; valider `case_id` avant toute lecture ; ne jamais signaler d'échec après qu'une paire `validated` a été persistée ; borner `update_report` au seul statut `draft`, sans transition vers `exported` (réservée à la Story 8.4) ; lever l'exception typée en échec -- centralise les invariables de la story.
- [x] `backend/src/iryx/reporting/__init__.py` -- exporter les nouveaux symboles publics -- point d’entrée stable pour l’orchestrateur.
- [x] `backend/migrations/versions/009_create_report_and_audit_tables.py` -- créer `reports` et `audit_events` (`revision="009"`, `down_revision="008"`), index et contraintes, dont l'unicité `(case_id, version, format)`, un `sha256` lowercase hexadécimal sur 64 caractères pour `reports` et `audit_events`, et des clés étrangères `audit_events` en `RESTRICT` afin qu'aucune suppression ne réécrive la piste, avec `downgrade` miroir -- applique le schéma attendu sans écraser la migration `008`.
- [x] `backend/migrations/env.py` -- importer `iryx.reporting.models` et `iryx.audit.models` -- rend les tables visibles à `target_metadata`.
- [x] `backend/src/iryx/orchestrator/graph.py` -- dans `reporting_node`, conserver la garde H3 et le contrat sans contexte ; n'autoriser le mode externe que pour `h3_approved is True` **et** ni `h3_rejected` ni `local_report_mode` (un drapeau local périmé ou un refus force le gabarit local) ; effacer tout `local_report_mode` périmé lors d'une approbation explicite ; faire prévaloir le `user_id` authentifié du runtime sur celui du checkpoint ; transmettre `user_id`, `h3_approved` et le pseudonymiseur partagé au service ; envelopper toute erreur de génération dans `ReportGenerationFailedException` ; générer et persister le rapport uniquement si `db` et `case_id` sont disponibles, puis renseigner `report` (génération, version, formats avec id/sha256/statut) et `context["report_generation_id"]` -- relie l'agent au cycle d'investigation sans casser les tests de nœud isolé.
- [x] `backend/src/iryx/orchestrator/services.py` -- injecter dans le runtime context le `user_id`, le `pseudonymizer` utilisé pour l'aperçu H3 et le `db` ; faire de même pour le chemin `resume_investigation` qui atteint `reporting_node` ; échouer avec `ReportGenerationFailedException` si le jeton de pseudonymisation ne peut pas être restauré ou persisté dans le checkpointer, plutôt que de retomber sur un pseudonymiseur neuf ; effacer `local_report_mode` lors d'une approbation H3 explicite ; lorsqu'aucun snapshot n'existe encore, n'ensemencer que `case_id`, `run_id`, `iteration_count`, `error_count`, `status` et `current_phase="gate_h3"`, sans jamais poser `h1_approved` ni `h2_approved` ; ne restaurer le jeton que sur un chemin de reprise qui atteint `reporting` -- garantit que le rapport est généré avec la même table de pseudonymes que celle approuvée à H3 et avec le contrôle d'accès de l'utilisateur.
- [x] `backend/tests/unit/test_finding_migration.py`, `backend/tests/unit/test_investigation_migration.py`, `backend/tests/unit/test_timeline_migration.py` -- remplacer toutes les assertions de head `["008"]` par `["009"]` -- maintient l’unicité du head Alembic.
- [x] `backend/tests/unit/test_report_migration.py`, `backend/tests/unit/test_report_models.py`, `backend/tests/unit/test_rapporteur_agent.py`, `backend/tests/unit/test_report_compiler.py`, `backend/tests/unit/test_report_service.py` -- ajouter les tests ciblés (upgrade/downgrade, contraintes, hash, modes LLM, exclusion des findings `proposed`, immuabilité/versionnage) -- couvre la matrice I/O.
- [x] `backend/tests/unit/test_orchestrator_graph.py` -- étendre les tests du nœud `reporting` avec un contexte `db`/pseudonymiseur/client LLM factice pour les chemins approuvé, refusé et sans verdict -- verrouille l’intégration et la barrière H3.

**Acceptance Criteria:**
- Given la migration `009` appliquée, when `alembic upgrade head` est exécuté, then un seul head existe et les tables `reports` et `audit_events` sont présentes avec leurs contraintes et index.
- Given un dossier avec contexte, preuves, observations et constats validés de criticités variées, when le rapport est généré, then les deux documents contiennent ces sections : résumé managérial, périmètre, méthodologie, chaîne des preuves, observations, constats validés avec criticité, chronologie et limites.
- Given un rapport `validated` en base, when la génération est relancée avec un contenu différent, then une nouvelle paire de lignes est insérée avec `version` supérieure et `generation_id` distinct, et les anciennes lignes restent bit à bit identiques.
- Given un rapport scellé, when son empreinte est recalculée depuis le contenu stocké, then elle est égale à `Report.sha256` pour les deux formats.
- Given un utilisateur non habilité sur le dossier, when il tente de générer un rapport via le service ou via `reporting_node`, then aucun rapport n’est créé et l’accès est refusé avant toute lecture du dossier.
- Given un `RapporteurAgent` construit sans `h3_approved=True`, when `generate()` est appelé, then le gabarit local est utilisé et aucun client LLM n’est contacté ; avec `h3_approved=True`, le client est `LLMRole.RAPPORTEUR`.
- Given une réponse LLM contenant un titre de constat non validé, when l’agent la parse, then la génération échoue sans rapport persisté ; la section `constats_valides` est toujours reconstruite depuis `facts`.
- Given deux générations concurrentes pour le même dossier, when elles calculent la version, then une seule paire de lignes est persistée pour chaque version et la seconde tente avec un nouveau `generation_id`.
- Given un aperçu H3 pseudonymisé, when le rapport est généré, then le même pseudonymiseur (ou son jeton restauré) est utilisé, de sorte qu’un même identifiant technique garde le même pseudonyme.
- Given une suppression de dossier ou d’utilisateur, when la piste `audit_events` contient des lignes liées, then la suppression est refusée plutôt que de cascader ou de réécrire `actor_id`.
- Given un test de migration, when la table est inspectée, then les contraintes `CHECK`, l’unicité `(case_id, version, format)` et le format hexadécimal de `sha256` sont explicitement vérifiés.
- Given `h3_approved=True` et `local_report_mode=True` (drapeau périmé), when `reporting_node` est appelé, then seul le gabarit local est utilisé, aucun client LLM n'est contacté et le drapeau périmé n'est pas réintroduit lors d'une approbation explicite.
- Given un jeton de pseudonymisation corrompu ou une écriture de checkpointer en échec, when la reprise génère le rapport, then la génération échoue avec `REPORT_GENERATION_FAILED` plutôt que d'utiliser un pseudonymiseur neuf.
- Given une réponse LLM citant un constat qui n'est dans aucun `facts` validé, when l'agent la parse, then la génération échoue sans rapport persisté, y compris si le titre n'était pas connu comme constat non validé.
- Given une ligne `draft`, when `update_report` tente de la promouvoir en `validated` avec un contenu arbitraire, then la promotion est refusée ; seul `generate_report` crée des lignes `validated`.
- Given les métadonnées ORM compilées pour PostgreSQL et pour SQLite, when `create_all` ou `autogenerate` est exécuté, then les `CHECK` hexadécimaux utilisent une syntaxe valide pour chaque dialecte et ne dérivent pas de la migration `009`.
- Given deux appels de génération avec le même `generation_id` fourni par l'appelant, when ils persistent, then ils produisent deux identifiants distincts ; l'appelant ne peut pas fixer `generation_id`.
- Given un utilisateur authentifié distinct de celui du checkpoint, when `reporting_node` est appelé, then l'utilisateur authentifié prévaut pour l'autorisation.
- Given un aperçu H3 demandé avant la première exécution du graphe, when le jeton est persisté dans le checkpointer, then aucun drapeau `h1_approved` ni `h2_approved` n'est fabriqué et la phase reste `gate_h3`.
- Given `h3_approved=True` sans pseudonymiseur injecté au niveau du service, when `generate_report` est appelé, then la génération échoue avec `REPORT_GENERATION_FAILED` au lieu d'instancier un pseudonymiseur neuf.
- Given une mention de constat sans indice de criticité ni préfixe « constat » dans une réponse LLM, when la mention ne correspond à aucun constat validé, then la génération échoue sans rapport persisté.
- Given une ligne `draft`, when `update_report` tente de lui attribuer le statut `exported`, then la transition est refusée.
- Given un `case_id` mal formé, when `generate_report` est appelé, then l'erreur est enveloppée avec `REPORT_GENERATION_FAILED` et journalisée sans trace.
- Given une paire `validated` déjà persistée, when le rafraîchissement des objets échoue après le commit, then l'appel ne signale pas d'échec et renvoie les lignes persistées.
- Given un jeton de pseudonymisation intact mais une reprise qui n'atteint pas `reporting`, when `resume_investigation` est appelé, then la restauration du jeton n'est pas imposée.

## Design Notes

La structure canonique est sérialisée une seule fois, puis chaque format est haché sur ses propres octets : le JSON utilise `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` et le Markdown son texte rendu exact. Le hash porte donc sur ce qui est réellement persisté, pas sur une resérialisation approximative.

Un `generation_id` regroupe les deux formats d’une même exécution ; `version` ordonne les générations successives. Le service refuse toute mutation d’une ligne `validated` et crée une nouvelle génération à la place, sans attendre le trigger d’audit de la Story 8.5.

`reporting_node` ne conserve son comportement de phase que lorsqu’aucune session DB et aucun `case_id` ne sont disponibles : cela préserve les tests existants de nœud isolé tout en activant la génération dans le graphe réel.

L’autorisation n’est pas optionnelle sur le chemin utilisateur : `user_id` est propagé depuis le runtime context jusqu’au `CaseService`, et le mode externe est conditionné à `h3_approved is True` (jamais à une conversion booléenne d’une chaîne). Le pseudonymiseur utilisé pour l’aperçu H3 est injecté dans le même runtime context que le rapport, afin que la table chiffrée par dossier reste la même entre l’approbation et la rédaction.

La concurrence est maîtrisée par une contrainte d’unicité `(case_id, version, format)` : en cas de conflit, le service réessaie avec un nouveau `generation_id` et une version recalculée. L’unicité et les contraintes `CHECK` sont vérifiées dans les tests de migration, pas seulement déduites de l’ORM.

La piste `audit_events` est append-only dès sa création : ses clés étrangères utilisent `RESTRICT`, et son empreinte est validée comme 64 caractères hexadécimaux minuscules. Le service et le trigger d’audit restent néanmoins à la Story 8.5 ; aucune écriture n’est ajoutée ici.

Le mode externe est une conjonction stricte : `h3_approved is True`, ni `h3_rejected`, ni `local_report_mode`. Un drapeau local laissé par un refus antérieur est effacé lors d'une approbation explicite, et le `user_id` authentifié du runtime l'emporte sur toute valeur persistée dans un checkpoint. La continuité de pseudonymisation est une condition de succès : si le jeton ne peut être restauré ou écrit dans le checkpointer, la génération échoue avec `REPORT_GENERATION_FAILED` plutôt que de produire un rapport dont les pseudonymes ne correspondent plus à l'aperçu approuvé.

La liste des constats autorisés est l'unique source de vérité : toute mention d'un titre qui n'est pas un constat validé fourni dans `facts`, y compris un titre inventé par le LLM, fait échouer la génération dans n'importe quelle section. Est considérée comme mention détectable toute clé structurée de titre, toute ligne précédée d'une criticité entre crochets, toute phrase introduite par « constat » ou « finding » et toute correspondance exacte avec un titre non validé transmis ; chaque extrait détecté doit correspondre exactement à un constat validé ou à sa forme pseudonymisée. La promotion en `validated` est réservée à `generate_report` : `update_report` ne modifie que des lignes `draft`, refuse le statut `exported` et n'accepte ni `generation_id` appelant ni contenu non compilé comme rapport validé. Les `CHECK` des métadonnées ORM sont portables par dialecte pour éviter toute divergence avec la migration `009`.

Le checkpointer n'est jamais utilisé pour inventer une approbation : l'ensemencement d'un état consécutif à un aperçu H3 avant la première exécution ne pose que l'identité du dossier, la phase `gate_h3` et les compteurs, et laisse les verdicts H1/H2 à leurs portes respectives. La continuité de pseudonymisation est exigée dès la frontière du service : sans pseudonymiseur injecté en mode externe, la génération échoue, ce qui rend la garde de l'agent effective. La restauration du jeton reste limitée au chemin qui atteint réellement `reporting`, afin qu'un jeton obsolète ne bloque pas une reprise sans rapport.

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- expected: suite complète verte, y compris les nouveaux tests de rapport et de migration.
- `cd backend && uv run ruff check src tests` -- expected: `All checks passed!`.
- `cd backend && uv run pytest -q tests/unit/test_alembic.py tests/unit/test_report_migration.py` -- expected: head unique `009`, `upgrade` et `downgrade` offline sans erreur.
- Tests ciblés supplémentaires attendus : chemin `resume_investigation` avec `db` fourni uniquement par le runtime context, y compris la persistance du jeton de pseudonymisation après aperçu H3 et sa restauration à l'identique après reprise ; contenu des deux rapports cloisonné par dossier ; échec de la seconde insertion sans ligne résiduelle ; `h3_approved` strict au niveau du nœud comme de l'agent ; priorité du gabarit local en cas de drapeaux combinés ; agent sans approbation sans appel LLM ; unicité de version et contraintes de migration ; compilation ORM sous les dialectes PostgreSQL et SQLite ; promotion `draft`→`validated` refusée ; `generation_id` appelant ignoré ; titre de constat non validé transmis par le service puis rejeté ; titre inventé rejeté dans toute section ; enveloppe typée `REPORT_GENERATION_FAILED` au niveau du nœud ; autorisation de `list_reports` et `update_report` pour un outsider ; comportement `RESTRICT` des FKs `audit_events` sur suppression réelle ; présence de constats/preuves dans le contexte du test de nœud approuvé ; absence de drapeaux H1/H2 fabriqués lors d'un aperçu avant première exécution ; échec typé du service en mode externe sans pseudonymiseur ; mention de constat sans indice détectée et rejetée ; refus de la transition `draft`→`exported` ; `case_id` mal formé enveloppé ; rafraîchissement après commit sans faux échec ; jeton ignoré sur une reprise hors `reporting` ; approbation et refus simultanés au nœud ; approbation après refus avec nettoyage de `local_report_mode` ; reprise approuvée avec client instrumenté et même pseudonyme que l'aperçu ; exclusion d'un constat, d'une preuve et d'une observation d'un second dossier ; assertion du SQL PostgreSQL de la migration sur les deux colonnes `sha256` ; immutabilité d'une ligne `validated` via `update_report` ; `ON DELETE CASCADE` de `reports.case_id` vérifié par suppression réelle.

## Spec Change Log

### 2026-11-25 — Revue 1 (loopback)
- Déclencheur : quatre findings `high` et plusieurs findings `medium` montrant que le spéc laissait des invariants non vérifiables (approbation H3 implicite, concurrence de version, continuité du pseudonymiseur, cloisonnement du nœud, append-only de `audit_events`).
- Amendements : tâches `rapporteur_agent.py`, `services.py`, `migration 009`, `graph.py` et `orchestrator/services.py` rendues explicites ; critères d'acceptation et notes de conception renforcés ; vérifications ciblées ajoutées. Le bloc `<intent-contract>` n'a pas été modifié.
- État connu évité : un rapport externe pouvait être rédigé sans `h3_approved` explicite, deux générations pouvaient partager une version, le pseudonymiseur d'aperçu pouvait différer de celui du rapport, et une réponse LLM pouvait inclure un constat non validé.
- KEEP : conserver la porte H3 infranchissable, le gabarit local sur refus, les huit sections canoniques, le hachage SHA-256 des octets exacts persistés, les deux lignes par génération, l'incrément de `version`, les lectures cloisonnées par `case_id`, la migration `009`, l'absence d'endpoints 8.4 et d'écritures/trigger 8.5, le contrat de nœud isolé, ainsi que la suite verte (908 tests) et `ruff` propre.

### 2026-11-25 — Revue 2 (loopback)
- Déclencheur : les couches de revue ont établi six findings `high` et dix-huit `medium` dont cinq défauts de spécification : combinaison non définie de `h3_approved`/`local_report_mode`, repli silencieux sur un pseudonymiseur neuf, titre de constat inventé non filtré, promotion `draft`→`validated` avec contenu arbitraire, `CHECK` ORM non portables et `generation_id` fixable par l'appelant.
- Amendements : tâches `rapporteur_agent.py`, `services.py`, `models.py`, `audit/models.py`, `graph.py` et `orchestrator/services.py` durcies ; sept critères d'acceptation ajoutés ; notes de conception et vérifications ciblées étendues. Le bloc `<intent-contract>` n'a pas été modifié.
- État connu évité : un envoi LLM externe pouvait survivre à un drapeau local périmé, un rapport pouvait être scellé avec des pseudonymes différents de ceux approuvés, un constat inexistant pouvait être cité dans une section libre, une ligne `validated` pouvait être créée hors compilateur, et les métadonnées ORM pouvaient diverger de la migration.
- KEEP : conserver la porte H3 infranchissable, le gabarit local sur refus et en mode local, les huit sections canoniques, le hachage SHA-256 des octets exacts persistés, les deux lignes par génération, l'incrément de `version` sous verrou, l'unicité `(case_id, version, format)`, les lectures cloisonnées par `case_id`, la migration `009`, les FKs `audit_events` en `RESTRICT`, l'absence d'endpoints 8.4 et d'écritures/trigger 8.5, le contrat de nœud isolé, la suite verte (907 tests) et `ruff` propre.

### 2026-11-25 — Revue 3 (loopback)
- Déclencheur : la troisième passe a relevé quatre défauts de spécification : l'ensemencement du checkpointer avant la première exécution fabriquait des verdicts H1/H2, le service remplaçait un pseudonymiseur absent par une instance neuve et rendait la garde de l'agent inatteignable, la notion de « mention de titre » restait indéfinie malgré l'interdiction absolue, et `update_report` autorisait une transition vers `exported`.
- Amendements : tâches `orchestrator/services.py`, `reporting/services.py` et `rapporteur_agent.py` durcies ; sept critères d'acceptation ajoutés ; notes de conception et vérifications ciblées étendues. Le bloc `<intent-contract>` n'a pas été modifié.
- État connu évité : un aperçu H3 pouvait enregistrer des approbations inexistantes, un rapport externe pouvait être rédigé avec une table de pseudonymes différente de celle approuvée, un titre inventé sans indice textuel pouvait être scellé, et une ligne `draft` pouvait acquérir le statut `exported` hors de la Story 8.4.
- KEEP : conserver la porte H3 infranchissable, le gabarit local sur refus et en mode local, les huit sections canoniques, le hachage SHA-256 des octets exacts persistés, les deux lignes par génération, l'incrément de `version` sous verrou, l'unicité `(case_id, version, format)`, les lectures cloisonnées par `case_id`, la migration `009`, les FKs `audit_events` en `RESTRICT`, l'absence d'endpoints 8.4 et d'écritures/trigger 8.5, le contrat de nœud isolé, la suite verte (919 tests) et `ruff` propre.

### 2026-11-26 — Revue 4 (patch, sans amendement)
- Déclencheur : la quatrième passe a relevé 43 findings dont aucun n'était un défaut de spécification ; les écarts réels concernaient la surcharge du contexte, la cohérence des métadonnées scellées, l'autorisation de `update_report`, la pseudonymisation, la normalisation des verdicts et l'alignement migration/métadonnées.
- Décision : `review_loop_iteration` reste à 3, le bloc `<intent-contract>` et les tâches ne sont pas modifiés. Les correctifs sont appliqués sur l'arbre courant puis revérifiés.
- KEEP : conserver la porte H3 infranchissable, le gabarit local sur refus et en mode local, les huit sections canoniques, le hachage SHA-256 des octets exacts persistés, les deux lignes par génération, l'incrément de `version`, le cloisonnement par `case_id`, la migration `009`, les FKs `audit_events` en `RESTRICT`, l'absence d'endpoints 8.4 et de service/trigger 8.5, le contrat de nœud isolé, la suite verte (958 tests) et `ruff` propre.

### 2026-11-26 — Revue 5 (patch, sans amendement)
- Déclencheur : la cinquième passe a relevé 32 signaux dont aucun n'était un défaut de spécification ; les écarts réels concernaient le câblage du client LLM en production, la pseudonymisation des titres exclus, le timeout, la détection des titres et la cohérence de `update_report`.
- Décision : `review_loop_iteration` reste à 3, le bloc `<intent-contract>` et les tâches ne sont pas modifiés. Les correctifs sont appliqués sur l'arbre courant puis revérifiés.
- KEEP : conserver la porte H3 infranchissable, le gabarit local sur refus et en mode local, les huit sections canoniques, le hachage SHA-256 des octets exacts persistés, les deux lignes par génération, l'incrément de `version`, le cloisonnement par `case_id`, la migration `009`, les FKs `audit_events` en `RESTRICT`, l'absence d'endpoints 8.4 et de service/trigger 8.5, le contrat de nœud isolé, la suite verte (980 tests) et `ruff` propre.

## Review Triage Log

### 2026-11-25 — Review pass
- verdicts: 34 findings — high 4, medium 19, low 7, false 4, maybe-false 0
- findings:
  - `[medium]` `[defer]` Le contexte Epic 8 régénéré perd les identifiants FR/NFR/D — la correction modifierait un fichier de contexte agent, inscrit dans `deferred`.
  - `[false]` `[reject]` Les critères d'acceptation sont rédigés dans le spec — c'est la production attendue du flux `bmad-build-auto`, pas un défaut.
  - `[false]` `[reject]` FR26 est scindé entre 8.3 et 8.4 — le contrat d'intent exclut explicitement les endpoints de téléchargement.
  - `[false]` `[reject]` Les garde-fous sont testés avec des substituts — l'isolement unitaire est normal et le chemin réel est couvert par le finding V1.
  - `[false]` `[reject]` Les assertions de head passent de `008` à `009` — la révision `008` est occupée, la mise à jour est obligatoire.
  - `[high]` `[bad_spec]` `reporting_node` ne transmet aucun `user_id` — `CaseService.get_case_by_id` ignore l'appartenance quand il vaut `None` ; la propagation doit être spécifiée.
  - `[medium]` `[bad_spec]` `user_id` est optionnel dans `generate_report`/`list_reports` — un appelant interne peut contourner le contrôle d'accès ; le spec doit définir le périmètre de confiance.
  - `[medium]` `[bad_spec]` `update_report` n'est pas cloisonné par `case_id`/`user_id` — une ligne `draft` d'un autre dossier pourrait être lue ou mutée ; le spec ne définit pas ce cloisonnement.
  - `[medium]` `[patch]` `update_report` accepte un `sha256` appelant — le correctif minimal est de toujours recalculer depuis `content` ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[reject]` Aucun trigger DB d'immutabilité — le contrat d'intent confie explicitement le trigger à la Story 8.5.
  - `[medium]` `[bad_spec]` Aucune unicité `(case_id, version, format)` — deux générations concurrentes peuvent produire une paire dupliquée ; le spec doit imposer la contrainte et le retry.
  - `[medium]` `[bad_spec]` Une reprise de nœud crée une nouvelle génération — le comportement doit être explicitement choisi entre idempotence et régénération.
  - `[high]` `[bad_spec]` La voie LLM externe n'impose que les clés de sections — un constat halluciné ou une valeur brute peut être scellé ; le contrat d'intent exige uniquement des constats validés.
  - `[medium]` `[bad_spec]` Le pseudonymiseur instancié à la volée ne réutilise pas le jeton de l'aperçu H3 — les pseudonymes approuvés peuvent différer de ceux envoyés au LLM.
  - `[medium]` `[bad_spec]` `audit_events.case_id` cascade et `actor_id` passe à `NULL` — la piste annoncée append-only est réécrite par une suppression ; le schéma doit utiliser `RESTRICT`.
  - `[low]` `[patch]` `audit_events.payload_sha256` ne valide que la longueur — ajouter un `CHECK` hexadécimal minuscule ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[defer]` Le contexte Epic 8 régénéré supprime les références de traçabilité — même cause que la première entrée, route `defer` pour fichier de contexte agent.
  - `[low]` `[reject]` Les commandes de vérification contiennent un chemin absolu — la correction éditerait le spec, ce que la règle de triage interdit.
  - `[low]` `[patch]` Le test de migration n'affirme pas les `CHECK` — ajouter les assertions ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[low]` `[patch]` Le cycle `draft → validated → exported` n'est pas testé — ajouter des tests ciblés ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[patch]` `exc_info=True` peut journaliser des fragments sensibles — retirer la trace ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[bad_spec]` La concurrence lit le `max(version)` sans verrou — même cause que l'entrée sur l'unicité, routée `bad_spec`.
  - `[low]` `[patch]` `refresh()` après commit peut échouer après persistance — corriger le libellé d'erreur ou l'ordre ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[bad_spec]` `update_report` sans `user_id` ni `case_id` — même cause que l'entrée service, routée `bad_spec`.
  - `[medium]` `[patch]` `sha256` fourni par l'appelant stocké tel quel — même cause que l'entrée précédente, routée `patch`.
  - `[low]` `[patch]` `status` arbitraire provoque une `IntegrityError` brute — valider via `ReportStatus` ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[patch]` Une erreur de construction du service échappe sans code typé — envelopper dans `ReportGenerationFailedException` ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[patch]` `bool("false")` est traité comme une approbation — utiliser `is True` ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[high]` `[bad_spec]` `RapporteurAgent` ouvre le mode externe par défaut — le spec doit imposer un `h3_approved` explicite avant tout appel réseau.
  - `[low]` `[patch]` Le `CHECK` de `sha256` n'impose pas les hexadécimaux — même cause que l'entrée sur `payload_sha256`, routée `patch`.
  - `[high]` `[bad_spec]` Aucun filtrage post-parse des constats — même cause que l'entrée sur le LLM externe, routée `bad_spec`.
  - `[medium]` `[patch]` Le chemin production via `get_runtime_context()` n'est pas testé — la couche a fourni la preuve ; ajouter le test de reprise ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[patch]` Les faits collectés ne sont pas testés pour l'exclusion du contenu d'un autre dossier — la couche a fourni la preuve ; ajouter des assertions distinctes ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.
  - `[medium]` `[patch]` L'échec de la seconde insertion n'est pas testé — la couche a fourni la preuve ; ajouter le test d'atomicité ; reporté au prochain passage car un `bad_spec` déclenche la re-dérivation.

### 2026-11-25 — Review pass (boucle 2)
- verdicts: 40 findings — high 6, medium 24, low 2, false 7, maybe-false 1
- findings:
  - `[medium]` `[patch]` Le test de nœud approuvé ne contient ni constat validé ni preuve — la ligne 1 de la matrice n'est prouvée qu'au service ; correctif de fixture et d'assertions reporté à la re-dérivation car un `bad_spec` est présent.
  - `[medium]` `[patch]` L'exclusion des constats non validés n'est testée qu'au service — mêmes données et assertions ajoutées au nœud ; correctif reporté à la re-dérivation.
  - `[medium]` `[patch]` Le wrapping `REPORT_GENERATION_FAILED` du nœud n'a aucun test — test de nœud avec service en échec ; correctif reporté à la re-dérivation.
  - `[false]` `[reject]` La régénération n'est pas testée au nœud — la ligne 6 de la matrice ne nomme pas le nœud et le service prouve la nouvelle génération ; aucune divergence réelle.
  - `[false]` `[reject]` `user_id` est une précondition supplémentaire du nœud — c'est l'implémentation du cloisonnement exigé par la boundary et par l'amendement de la revue 1, pas un écart.
  - `[high]` `[bad_spec]` `h3_approved` et `local_report_mode` peuvent coexister et le LLM externe est appelé — amendement : conjonction stricte et effacement du drapeau périmé.
  - `[medium]` `[patch]` Le chemin réel `resume_investigation` n'est pas couvert — test de reprise avec aperçu H3 ; correctif reporté à la re-dérivation.
  - `[high]` `[bad_spec]` Drapeaux H3 combinés : l'approbation gagne sur le refus et le mode local — même racine que l'amendement sur la priorité.
  - `[high]` `[bad_spec]` `arbitrate_gate_h3` ne retire pas `local_report_mode` lors d'une approbation — amendement : nettoyage explicite du drapeau.
  - `[medium]` `[bad_spec]` Les `CHECK` ORM utilisent `GLOB` pour tous les dialectes alors que la migration utilise une regex — amendement : expressions portables.
  - `[medium]` `[bad_spec]` `_resolve_report_pseudonymizer` avale l'erreur de restauration et revient à un pseudonymiseur neuf — amendement : échec typé sans repli.
  - `[high]` `[bad_spec]` Un titre de constat inventé par le LLM passe dans les sections libres — amendement : filtrage contre les seuls `facts` validés.
  - `[medium]` `[bad_spec]` `update_report` peut promouvoir un `draft` en `validated` avec un contenu arbitraire — amendement : transition interdite.
  - `[medium]` `[bad_spec]` `generation_id` fourni par l'appelant est accepté au premier essai et n'est pas unique — amendement : génération interne exclusive.
  - `[false]` `[reject]` `resume_investigation` retombe sur l'utilisateur du checkpoint — le routeur fournit toujours l'utilisateur authentifié et le repli ne concerne que les appels internes de confiance.
  - `[medium]` `[patch]` Aucun test ne couvre l'injection `db`/`user_id`/pseudonymiseur par `resume_investigation` — correctif reporté à la re-dérivation.
  - `[low]` `[patch]` Le comportement `RESTRICT` des FKs n'est vérifié que dans les métadonnées — test de suppression réelle ; correctif reporté à la re-dérivation.
  - `[medium]` `[patch]` L'autorisation de `list_reports`/`update_report` n'est pas testée pour un outsider — correctif reporté à la re-dérivation.
  - `[low]` `[reject]` Une preuve sans SHA-256 est signalée « non calculé » puis scellée — `Evidence.sha256` est nullable et le libellé est explicite ; un garde-fou serait disproportionné.
  - `[high]` `[bad_spec]` Refus H3 et approbation simultanés : le LLM externe reste appelable — même racine que la priorité H3.
  - `[medium]` `[patch]` Le `user_id` du checkpoint l'emporte sur celui du runtime dans `reporting_node` — inverser la priorité au profit de l'utilisateur authentifié ; correctif reporté à la re-dérivation.
  - `[medium]` `[bad_spec]` Un jeton corrompu provoque un repli silencieux — même racine que le finding sur la continuité.
  - `[medium]` `[bad_spec]` L'échec de persistance du jeton dans le checkpointer est avalé — même racine que le finding sur la continuité.
  - `[false]` `[reject]` Reprise sans `user_id` hérite de l'utilisateur du checkpoint — appels internes autorisés et routeur toujours authentifié.
  - `[medium]` `[bad_spec]` Sans pseudonymiseur partagé, une instance neuve est utilisée sur la voie externe — même racine que le finding sur la continuité.
  - `[false]` `[reject]` `for_role` pourrait renvoyer un client de mauvais rôle — `UnifiedLLMClient.for_role` construit toujours une instance avec le rôle demandé ; la souplesse ne concerne que les doubles de test.
  - `[maybe-false]` `[defer]` Un client lié à un event loop pourrait être réutilisé depuis un autre loop via le pont synchrone — affinité non démontrée ; inscrit dans `deferred` avec sévérité medium (unverified).
  - `[medium]` `[bad_spec]` Une ligne `draft` peut devenir `validated` avec du contenu arbitraire — même racine que la promotion non compilée.
  - `[medium]` `[bad_spec]` `GLOB` figé dans les métadonnées ORM — même racine que la portabilité des `CHECK`.
  - `[high]` `[bad_spec]` Un `local_report_mode` périmé change silencieusement le comportement — même racine que le nettoyage du drapeau.
  - `[medium]` `[bad_spec]` `report.status = ReportStatus(...)` autorise la promotion en `validated` — même racine que la promotion non compilée.
  - `[medium]` `[bad_spec]` Le pseudonymiseur d'aperçu peut différer de celui du rapport — même racine que le repli silencieux.
  - `[false]` `[reject]` Le rôle du client n'est pas vérifié après `for_role` — le client réel garantit le rôle demandé.
  - `[false]` `[reject]` La ligne `Case` est lue avant le contrôle d'appartenance — cette lecture sert à déterminer l'organisation dans `CaseService` ; aucune donnée de rapport n'est exposée avant le refus et le motif est antérieur à la story.
  - `[medium]` `[patch]` Le titre `PROPOSED_TITLE` n'est pas testé depuis le service avec une réponse LLM — ajouter le cas de bout en bout ; correctif reporté à la re-dérivation.
  - `[medium]` `[patch]` Le jeton d'aperçu H3 n'est pas vérifié après reprise — même correctif que le chemin réel de reprise.
  - `[medium]` `[patch]` `h3_approved="false"` n'est pas testé au niveau du nœud — ajouter le cas ; correctif reporté à la re-dérivation.
  - `[medium]` `[patch]` Le wrapping typé du nœud n'est pas testé — même correctif que le test de nœud en échec.
  - `[medium]` `[patch]` `list_reports`/`update_report` ne sont pas testés pour un outsider — même correctif que l'autorisation des lectures.
  - `[medium]` `[bad_spec]` Les `CHECK` ORM non portables ne sont pas compilés sous PostgreSQL — même racine que la portabilité des `CHECK`.

### 2026-11-25 — Review pass (boucle 3)
- verdicts: 35 findings — high 8, medium 17, low 6, false 4, maybe-false 0
- findings:
  - `[high]` `[bad_spec]` `_persist_report_pseudonym_token` fabrique `h1_approved=True`, `h2_approved=True` et `current_phase="gate_h3"` quand aucun snapshot existe — amendement : n'ensemencer que l'identité du dossier et la phase, jamais de verdict.
  - `[high]` `[bad_spec]` `generate_report` remplace un pseudonymiseur absent par une instance neuve même en mode externe — amendement : échec typé sans repli au niveau du service.
  - `[low]` `[patch]` `h3_rejected` est converti par `bool(...)`, donc une chaîne « false » force le mode local — normaliser les verdicts non booléens.
  - `[high]` `[bad_spec]` Un titre inventé sans marqueur de criticité ni préfixe « constat » échappe au filtrage — amendement : définir les formes détectables de mention et exiger leur correspondance exacte avec un constat validé.
  - `[low]` `[reject]` Une criticité inconnue est ramenée à `low` — `Finding.severity` est un `StrEnum`, la valeur invalide est injoignable depuis la base ; aucun écart réel.
  - `[medium]` `[patch]` Le retry de version est simulé par monkeypatch, pas par deux générations réelles — renforcer le test d'unicité.
  - `[medium]` `[patch]` Aucun test n'appelle `update_report` sur une ligne `validated` — ajouter le test d'immutabilité.
  - `[medium]` `[bad_spec]` `update_report` accepte une transition `draft`→`exported` avec du contenu arbitraire — amendement : statut cible unique `draft`.
  - `[medium]` `[patch]` `resume_investigation` valide le jeton même hors chemin de rapport — limiter la restauration au chemin qui atteint `reporting`.
  - `[low]` `[patch]` Le `ON DELETE CASCADE` de `reports.case_id` n'est pas vérifié de bout en bout — ajouter l'assertion de suppression.
  - `[medium]` `[patch]` La branche d'incompatibilité `report_pseudonym_case_id` n'est pas testée — ajouter le cas.
  - `[low]` `[reject]` `generated_at` n'est pas validé comme ISO-8601 — le service le génère lui-même ; aucun vecteur externe.
  - `[low]` `[patch]` Le spec est `in-review` alors que `sprint-status.yaml` marque 8.3 `done` — correction de suivi appliquée directement.
  - `[low]` `[reject]` L'affinité du client LLM asynchrone reste non vérifiée — déjà inscrite dans `deferred`, sans nouvelle information.
  - `[false]` `[reject]` La régénération est prouvée au service et non au nœud — lecture R2 retenue en boucle 2 ; pas de divergence nouvelle.
  - `[medium]` `[patch]` Le chemin approuvé n'est pas exercé via `graph.invoke`/`resume_investigation` — ajouter une reprise approuvée avec client instrumenté.
  - `[medium]` `[patch]` Le refus H3 via le graphe n'instrumente pas le client — ajouter l'assertion d'absence d'appel sur ce chemin.
  - `[medium]` `[patch]` Les déclencheurs d'erreur nommés ne sont pas conduits jusqu'au nœud — ajouter un test de nœud en échec de compilation ; l'enveloppe HTTP reste hors périmètre faute d'endpoints 8.4.
  - `[medium]` `[patch]` Le cloisonnement n'est pas testé au niveau du graphe — même correctif que le test de facts multi-dossiers.
  - `[false]` `[reject]` « H2 validé » est lu comme le statut DB des constats — lecture défendable et cohérente avec `get_validated_findings`.
  - `[false]` `[reject]` Un ORM `AuditEvent` est ajouté alors que le contrat nomme la migration — l'alignement des métadonnées est requis par le task de `env.py`.
  - `[false]` `[reject]` Les lignes 4 et 7 de la matrice sont alignées — aucune divergence à trier.
  - `[high]` `[bad_spec]` Le service ne reçoit pas de verdict `h3_rejected` explicite — même racine que la conjonction H3 ; le service doit refuser le mode externe sur verdict négatif.
  - `[high]` `[bad_spec]` L'instance neuve implicite rend la garde de l'agent inatteignable — même racine que le repli au service.
  - `[high]` `[bad_spec]` Une mention sans indice textuel persiste malgré l'interdiction — même racine que la définition des mentions détectables.
  - `[high]` `[bad_spec]` La racine du filtrage par indices est insuffisante — même amendement que les mentions détectables.
  - `[medium]` `[patch]` `facts["h3_rejected"]` n'est jamais alimenté — supprimer le garde mort ou exiger le verdict au service.
  - `[medium]` `[patch]` Un `case_id` mal formé laisse échapper une `ValueError` brute — envelopper dans `REPORT_GENERATION_FAILED`.
  - `[medium]` `[patch]` Un `refresh()` en échec après `commit()` laisse des lignes `validated` pour l'appelant — ne pas signaler d'échec après persistance.
  - `[medium]` `[patch]` Une approbation et un refus simultanés au nœud ne sont pas testés — ajouter le cas combiné.
  - `[medium]` `[patch]` Le nettoyage de `local_report_mode` après approbation n'est pas testé — ajouter le cas approbation après refus.
  - `[medium]` `[patch]` La reprise approuvée ne vérifie pas le jeton d'aperçu — même correctif que le chemin approuvé via le graphe.
  - `[medium]` `[patch]` Les faits d'un second dossier ne sont pas exclus dans un test de génération — ajouter constat, preuve et observation dans l'autre dossier.
  - `[medium]` `[patch]` La regex PostgreSQL de la migration n'est pas affirmée — capturer le SQL offline et vérifier les deux colonnes.
  - `[high]` `[bad_spec]` Le service remplace silencieusement le pseudonymiseur absent — même racine que le repli au service, routée `bad_spec`.

### 2026-11-26 — Review pass (boucle 4)
- verdicts: 43 findings — high 7, medium 27, low 1, false 8, maybe-false 0
- findings:
  - `[high]` `[patch]` `context.update(kwargs)` laisse l'appelant remplacer `facts`, `invalid_finding_titles` et le contexte DB — interdire la surcharge des clés réservées.
  - `[high]` `[patch]` Le contenu scellé porte un `generation_id`/`version`/`created_at` périmés par rapport à la ligne persistée — allouer ces valeurs avant compilation et les réinjecter dans `ReportContent`.
  - `[high]` `[patch]` `update_report` n'appelle `_authorize` que si `case_id` est fourni — exiger `case_id` hors appel interne et vérifier l'appartenance avant lecture.
  - `[medium]` `[patch]` Le nœud convertit aussi les erreurs d'autorisation en `REPORT_GENERATION_FAILED` — laisser remonter `InsufficientPermissionsException`.
  - `[high]` `[patch]` `_pseudonymize` retombe sur le texte brut si `pseudonymized_text` manque — échouer avec l'exception typée.
  - `[false]` `[reject]` Le contexte runtime fuirait entre requêtes — `_runtime_context` est un `ContextVar`, pas une variable globale.
  - `[medium]` `[patch]` `h3_rejected` et `local_report_mode` utilisent `bool(...)` au service et à l'agent — appliquer la normalisation stricte déjà retenue au nœud.
  - `[medium]` `[patch]` `generate_sync` réutilise une coroutine déjà consommée après une `RuntimeError` interne — détecter la boucle active avant de créer la coroutine.
  - `[medium]` `[patch]` `_resolve_client` considère un client sans attribut `role` comme Rapporteur — rejeter l'absence de rôle.
  - `[medium]` `[patch]` La migration utilise `postgresql.UUID` pour tous les dialectes alors que l'ORM utilise le type générique — aligner les types rendus.
  - `[medium]` `[patch]` Les noms de contraintes diffèrent entre migration et métadonnées — aligner les noms pour éviter l'autogenerate.
  - `[medium]` `[patch]` Toute `IntegrityError` est traitée comme conflit de version — ne réessayer que sur la violation d'unicité.
  - `[low]` `[patch]` Le test de contrainte ne vérifie que la truthiness — affirmer le nom de la contrainte violée.
  - `[medium]` `[patch]` Le retry reste simulé par monkeypatch — ajouter deux générations réelles et vérifier les identifiants distincts.
  - `[medium]` `[patch]` Cas de nœud absents : approbation et refus simultanés, verdict « false », échec typé via le graphe — ajouter les trois tests.
  - `[false]` `[reject]` « H2 validé » est lu au niveau DB — lecture déjà arbitrée en boucle 3, inchangée.
  - `[false]` `[reject]` La génération est déléguée au service — lecture en couches retenue depuis la boucle 2.
  - `[medium]` `[patch]` Le code et le statut 500 de `REPORT_GENERATION_FAILED` ne sont pas affirmés — ajouter les assertions sur `code` et `status_code`.
  - `[medium]` `[patch]` L'ancienne paire n'est pas relue après régénération — ajouter l'assertion d'identicité bit à bit.
  - `[medium]` `[patch]` La normalisation stricte n'existe qu'au nœud — même racine que le verdict `bool(...)`, routée `patch`.
  - `[false]` `[reject]` Le cloisonnement utilisateur est une extension de spécification — déjà arbitrée en boucle 3, inchangée.
  - `[false]` `[reject]` L'ORM `AuditEvent` accompagne la migration — déjà arbitré en boucle 3, inchangé.
  - `[medium]` `[patch]` La limite « pas de donnée brute vers le LLM externe » n'est pas garantie — même racine que le repli brut de `_pseudonymize`.
  - `[false]` `[reject]` Le test de nœud isolé est conservé — aucune divergence.
  - `[false]` `[reject]` Les constats validés et leur criticité sont reconstructeurs — aucune divergence.
  - `[high]` `[patch]` `update_report` sans `case_id` permet à n'importe quel utilisateur de muter un brouillon — même racine que l'autorisation manquante.
  - `[medium]` `[patch]` Le jeton restauré d'un autre dossier n'a pas de test dédié — ajouter le cas d'incompatibilité.
  - `[high]` `[patch]` Un pseudonymiseur mal formé envoie du texte brut au LLM — même racine que le repli brut.
  - `[medium]` `[patch]` La coroutine consommée masque l'erreur d'origine — même racine que le pont synchrone.
  - `[high]` `[patch]` Les métadonnées du document divergent de la ligne — même racine que l'allocation tardive.
  - `[medium]` `[patch]` `future.result()` n'a pas de délai — ajouter un timeout explicite à l'appel externe.
  - `[medium]` `[patch]` `update_report` accepte un `ReportContent` dont le `case_id` diffère de la ligne — rejeter l'incohérence.
  - `[high]` `[patch]` L'affirmation de cloisonnement par `case_id` est fausse sur `update_report` — même racine que l'autorisation manquante.
  - `[false]` `[reject]` Un titre inventé sans indice textuel persiste — la boucle 3 définit précisément les formes détectables ; le code conforme à cette définition n'est pas en faute.
  - `[high]` `[patch]` La frontière « jamais de donnée brute » n'est pas absolue — même racine que le repli brut.
  - `[medium]` `[patch]` Un client sans rôle passe la vérification — même racine que la valeur par défaut de `_resolve_client`.
  - `[medium]` `[patch]` Un titre structuré imbriqué n'est pas détecté — `_walk_strings` le collecte mais `_extract_mentioned_titles` l'ignore.
  - `[medium]` `[patch]` Le code et le statut 500 ne sont pas testés — même racine que l'assertion manquante.
  - `[medium]` `[patch]` L'enregistrement des tables dans `target_metadata` n'est pas vérifié — ajouter le test d'environnement Alembic.
  - `[medium]` `[patch]` L'échec d'écriture du jeton dans le checkpointer n'est pas testé — ajouter le cas de panne.
  - `[medium]` `[patch]` L'approbation et le refus simultanés ne sont pas testés au nœud — même correctif que le cas de nœud combiné.
  - `[medium]` `[patch]` Le nettoyage après approbation suivant un refus n'est pas testé — ajouter le cas rejet puis approbation.
  - `[medium]` `[patch]` Le title structuré imbriqué non détecté est confirmé par exécution directe — même racine que la collecte ignorée.

### 2026-11-26 — Review pass (boucle 5, après patch)
- verdicts: 32 signaux (15 blind hunter, 10 edge cases, 2 verification gap, 5 divergences descriptives de l'alignment) — aucun `bad_spec`, aucun `intent_gap`.
- Les lectures descriptives de l'alignment (service en couches, statut DB des constats, régénération au service, exception typée sans endpoint 8.4, `local_report_mode` comme verdict local) reprennent des arbitrages déjà consignés : `[false]` `[reject]`.
- findings retenus (`patch`, racines vérifiées dans le code) :
  - `[high]` `[patch]` Le chemin de production n'injecte jamais de client LLM (`_inject_runtime` ne porte que `db`, `user_id`, `pseudonymizer`) — résoudre `get_llm_client(role=LLMRole.RAPPORTEUR)` dans `reporting_node` en mode externe et ajouter le test de reprise sans injection manuelle.
  - `[high]` `[patch]` Les titres non validés sont pseudonymisés dans le prompt mais comparés en clair — pseudonymiser aussi la liste d'exclusion avec le pseudonymiseur partagé et valider les deux formes.
  - `[high]` `[patch]` `RapporteurAgent.generate` applique encore `payload.update(kwargs)` — refuser explicitement les clés réservées (`facts`, `case`, `generation_id`, `llm_client`, …).
  - `[high]` `[patch]` `update_report` accepte un contenu dont les métadonnées divergent de la ligne — réinjecter `generation_id`, `version`, `created_at` depuis la ligne avant compilation.
  - `[high]` `[patch]` Le chemin `update_report` avec texte brut contourne la règle « seuls les findings validés » — appliquer la même validation de titres, avec les titres validés et non validés relus du dossier.
  - `[medium]` `[patch]` `generate_sync` n'applique le délai qu'à la branche avec event loop actif — unifier les deux branches dans l'exécuteur avec timeout et annuler l'appel `complete()` sous-jacent.
  - `[medium]` `[patch]` `_BRACKETED_TITLE_RE` ignore les marqueurs de liste (`- [high] …`) — normaliser le préfixe avant correspondance.
  - `[medium]` `[patch]` `_INTRODUCED_TITLE_RE` tronque les titres contenant des points et rejette la prose ordinaire — exiger un séparateur explicite et préférer la correspondance du titre complet.
  - `[medium]` `[patch]` `validate_canonical_sections` ne vérifie pas l'appariement clé ↔ titre canonique — imposer la paire exacte.
  - `[medium]` `[patch]` `render_json` n'utilise pas `default=str` — sérialiser les valeurs UUID/datetime du métadonnées sans erreur typée.
  - `[medium]` `[patch]` Un constat validé au titre vide est silencieusement omis — échouer avec l'exception typée.
  - `[medium]` `[patch]` `get_anonymized_preview` peut écraser un jeton déjà approuvé — refuser l'écrasement d'un jeton divergent.
  - `[low]` `[patch]` `list_reports` enveloppe `ValidationException` en erreur 500 — la laisser remonter comme `update_report`.
  - `[medium]` `[patch]` Ajouter les tests : chemin approuvé sans injection manuelle, titre non validé contenant une donnée personnelle, timeout des deux branches, titre entre crochets précédé d'un marqueur, prose « constats valides… », appariement de section, `payload.update` refusé, titre validé vide, écrasement de jeton, type `payload JSONB` dans le SQL PostgreSQL.
  - `[false]` `[reject]` Les noms de contraintes différeraient entre migration et ORM — la convention `ck_%(table_name)s_%(constraint_name)s` produit exactement les noms `ck_reports_*` de la migration.
  - `[false]` `[reject]` `review_loop_iteration` devrait passer à 4 — aucune divergence de spécification n'a été identifiée ; l'itération ne progresse que sur `bad_spec`. Le change log Revue 4 a été ajouté.

### 2026-11-26 — Review pass (boucle 6, après second patch)
- verdicts: 20 signaux (10 blind hunter, 7 edge cases dont 2 doublons, 3 verification gap, divergences descriptives sans nouveau finding) — aucun `bad_spec`, aucun `intent_gap`. Routing : 13 `patch`, 1 `defer`, 4 `reject`, 2 doublons.
- findings retenus (`patch`,racines vérifiées dans le code) :
  - `[high]` `[patch]` `get_llm_client(role=LLMRole.RAPPORTEUR)` est résolu hors du `try` de `reporting_node` — une panne de fabrique échappe en exception brute, non typée et non journalisée.
  - `[medium]` `[patch]` `_walk_title_values` ignore les valeurs non chaînes sous une clé `title`/`titre` — un titre inventé dans une liste structurée échappe au filtrage.
  - `[medium]` `[patch]` `_inject_runtime` conserve un `llm_client` périmé d'une requête précédente — ne conserver le client que s'il est explicitement fourni à l'injection.
  - `[medium]` `[patch]` `list_reports` valide `format` hors de la gestion de `ValidationException` — un format mal formé doit remonter en 422 comme un `case_id` mal formé.
  - `[medium]` `[patch]` `ReportOut.validate_enum_value` est un validateur no-op — rejeter explicitement les valeurs inconnues de `format`/`status`.
  - `[high]` `[patch]` Le garde-fou final de `generate_report` et `_validate_report_titles` ne comparent que les titres bruts — étendre l'exclusion aux formes pseudonymisées quand un pseudonymiseur est disponible.
  - `[medium]` `[patch]` Deux délais indépendants de 60 s : le `future.result` expire avant l'annulation interne de `complete()` — donner au délai interne une marge inférieure au délai externe.
  - `[medium]` `[patch]` `_RESERVED_AGENT_KWARGS` omet `run_id`, `case_title`, `timeline_events` et `incident_description` — ajouter ces clés réservées.
  - `[medium]` `[patch]` `_persist_pseudonymizer_token` ne vérifie pas le `pseudonymization_case_id` stocké — refuser un jeton provenant d'un autre dossier.
  - `[medium]` `[patch]` Tests manquants : forwarding de `current_user.id` par le router, titre non validé dans un corps `ReportContent` de `update_report`, absence de pseudonymiseur dans le contexte checkpointé, immutabilité du jeton via `get_anonymized_preview`.
  - `[false]` `[reject]` `**formats` exposerait des clés de premier niveau non déclarées — les clés sont imbriquées dans `report`, un champ déclaré de `InvestigationState`.
  - `[false]` `[reject]` `get_anonymized_preview` muterait le store avant le contrôle du jeton — le contrôle existe déjà avant `_persist_pseudonymizer_token`.
  - `[false]` `[reject]` `arbitrate_gate_h3` restaurerait le jeton hors chemin `reporting` — le refus H3 positionne explicitement `current_phase="reporting"` ; lecture déjà arbitrée.
  - `[false]` `[reject]` `sprint-status.yaml` resterait en `backlog` — la finalisation est volontairement différée après convergence.
  - `[deferred]` `[defer]` Concurrence de deux aperçus écrivant des jetons différents pour le même run — le checkpointer n'offre pas de mise à jour conditionnelle atomique vérifiée ; correctif hors périmètre de la Story 8.3, ajouté au frontmatter `deferred`.

### 2026-11-26 — Review pass (boucle 7, après troisième patch)
- verdicts: 18 signaux (13 blind hunter, 3 edge cases, 2 verification gap, divergences descriptives sans nouveau finding) — aucun `bad_spec`, aucun `intent_gap`. Routing : 7 `patch`, 2 `defer`, 9 `reject`.
- findings retenus (`patch`,racines vérifiées dans le code) :
  - `[high]` `[patch]` `_load_context` transmet l'ORM `Case` vivant à l'agent ; `_as_dict` énumère les relations lazy et peut exposer des titres `proposed` et l'email du créateur dans le prompt externe — transmettre un dict de colonnes.
  - `[high]` `[patch]` `_validate_report_titles` ne reconnaît que les titres validés bruts — étendre l'ensemble autorisé aux formes pseudonymisées.
  - `[high]` `[patch]` Un pseudonymiseur injecté sans store pour le dossier laisse `get_anonymized_preview` créer une table divergente avant de rejeter le jeton — restaurer le jeton stocké avant toute pseudonymisation.
  - `[medium]` `[patch]` `logger.info` après le commit n'est pas protégé : une erreur de journalisation ferait signaler un échec alors que la paire `validated` est persistée — envelopper dans `contextlib.suppress(Exception)`.
  - `[medium]` `[patch]` La coroutine de `generate_sync` est créée dans le thread appelant avant soumission — la créer dans le worker ou la fermer explicitement, et affirmer l'annulation dans les deux branches.
  - `[medium]` `[patch]` Ajouter les tests d'absence de données brutes dans le prompt, de présence de la section `chronologie` issue de la timeline projetée.
  - `[medium]` `[patch]` Corriger l'ordre du change log (Revue 3 avant Revue 4) et remplacer les chemins absolus de vérification par `cd backend && …` — appliqué directement au spec.
  - `[deferred]` `[defer]` Le verrou de ligne du dossier reste pris pendant l'appel LLM (jusqu'à 60 s) — restructuration transactionnelle hors périmètre.
  - `[deferred]` `[defer]` `reports.generation_id` n'a pas de `CHECK` de format UUID — contrainte non demandée par le contrat, ajout différé.
  - `[false]` `[reject]` `_extract_sections` n'appliquerait pas les alias de sections — `ReportSection` résout déjà `summary`, `findings` et les libellés canoniques via `_SECTION_ALIASES`.
  - `[false]` `[reject]` Le service n'exigerait pas de jeton en mode externe — la continuité est imposée à la frontière d'orchestration, seul endroit où le jeton existe ; lecture déjà arbitrée.
  - `[false]` `[reject]` La migration dupliquerait la classe de contrainte hexagonale — les migrations doivent rester autonomes ; duplication intentionnelle.
  - `[false]` `[reject]` `local_report_mode` autoriserait un rapport sans verdict — lecture R4(broad) déjà arbitrée en boucle 3.
  - `[false]` `[reject]` Un appel de nœud sans `user_id` générerait sans contrôle — `internal=True` est explicitement prévu par le contrat de service et les tests.
  - `[false]` `[reject]` La pseudonymisation des titres exclus écrirait de nouvelles correspondances — avec la restauration du jeton, le store déterministe réutilise les correspondances approuvées.

### 2026-11-26 — Review pass (convergence, après quatrième patch)
- verdicts: 18 signaux (12 blind hunter, 6 edge cases, 0 verification gap, divergences descriptives sans nouveau finding) — aucun `bad_spec`, aucun `intent_gap`. Routing : 6 `patch`, 12 `reject`. Détail : high 2, medium 3, low 1, false 12.
- findings retenus (`patch`, racines vérifiées dans le code) :
  - `[high]` `[patch]` `_opaque_free_text` ne masque que `case.title`, `case.description` et `evidence.original_name` — `observations` et `timeline` (ainsi que la liste `invalid_titles`) traversent encore le prompt externe en clair ; masquer récursivement tous les champs libres de ces collections et n'exposer au LLM que les formes pseudonymisées des titres exclus.
  - `[medium]` `[patch]` `_resolve_client` appelle `for_role(RAPPORTEUR)` sur un client déjà obtenu avec ce rôle par `reporting_node` — deux instances `UnifiedLLMClient`/`AsyncOpenAI` par rapport ; réutiliser le client quand son rôle est déjà `RAPPORTEUR`, sans supprimer la vérification de rôle.
  - `[medium]` `[patch]` `verdict_flag` n'accepte que les booléens et une petite liste de chaînes — un `h3_rejected=1` issu d'un checkpointer n'est pas reconnu comme un refus ; accepter l'entier `1` comme affirmatif sans assouplir `h3_approved is True`.
  - `[medium]` `[patch]` `test_version_conflict_retries_with_new_generation` ne démontre pas une seconde tentative réussie dans le même appel — ajouter un test où `_allocate_version` renvoie 1 puis 2 au sein d'un unique `generate_report`.
  - `[low]` `[patch]` `list_reports` n'est testé que pour un format mal formé — ajouter un test où un filtre `markdown` valide ne renvoie que les lignes correspondantes.
  - `[medium]` `[patch]` Ajouter les assertions d'absence des résumés d'observation et de chronologie dans le prompt externe.
  - `[false]` `[reject]` Le rapport scellé contiendrait des titres pseudonymisés au lieu des titres validés — choix explicite du spec (« constat validé ou sa forme pseudonymisée ») et test `test_external_mode_uses_shared_pseudonymizer_and_llm` : lecture déjà arbitrée.
  - `[false]` `[reject]` Un appelant direct pourrait fixer `generation_id`/`version` via le contexte de l'agent — le service remplace ces métadonnées avant compilation et persistance ; arbitrage de la boucle 1 conservé.
  - `[false]` `[reject]` Aucune vérification d'intégrité à la lecture — le contrat porte sur le scellement des octets persistés, pas sur une re-vérification à chaque lecture ; ajouter un tel contrôle étendrait la surface.
  - `[false]` `[reject]` `update_report` serait inatteignable en production — l'API `draft` est définie par la Story 8.3 indépendamment des producteurs futurs ; lecture déjà arbitrée.
  - `[false]` `[reject]` `get_anonymized_preview` ne contrôlerait pas l'appartenance au service — le routeur applique `verify_case_access` ; aucun endpoint 8.4 n'est ajouté.
  - `[false]` `[reject]` Le mode externe pourrait être actif sans `h3_approved` — `_external_allowed` exige `h3_approved is True` et l'absence de refus.
  - `[false]` `[reject]` Un pseudonymiseur sans correspondances enverrait du texte brut — `pseudonymize()` crée la table déterministe et le jeton approuvé est restauré avant tout appel.
  - `[false]` `[reject]` Un `user_id` chaîne JSON casserait la reprise — `_safe_uuid` parse strictement les chaînes UUID avant toute lecture.
  - `[false]` `[reject]` Une panne d'écriture du checkpointer après commit laisserait des rapports sans jeton — le jeton est persisté avant la génération, aucun checkpointer n'est écrit après le commit.
  - `[false]` `[reject]` Un endpoint `internal=true` contournerait l'autorisation — aucun `reporting/router.py` n'existe ; les endpoints 8.4 sont exclus.
  - `[false]` `[reject]` `_is_version_conflict` ne reconnaîtrait pas PostgreSQL — la contrainte `diag.constraint_name` et les deux variantes de message sont gérées.

### 2026-11-26 — Review pass (dernière passe)
- verdicts: 21 signaux (12 blind hunter, 7 edge cases dont 1 relance complète, 2 verification gap, divergences descriptives sans nouveau finding) — aucun `bad_spec`, aucun `intent_gap`. Routing : 8 `patch`, 2 `defer`, 11 `reject`.
- findings retenus (`patch`, racines vérifiées dans le code) :
  - `[medium]` `[patch]` `update_report` conserve les `metadata` fournies par l'appelant alors que `render_json` les sérialise et que `_validate_report_titles` ne voit que les sections — valider aussi le document rendu.
  - `[medium]` `[patch]` `generate_report` convertit une `ValidationException` (dossier valide mais absent) en 500 — l'ajouter à la tuple des exceptions rejouées telles quelles, comme `list_reports`.
  - `[medium]` `[patch]` `_walk_strings` ignore les clés de dictionnaire et `_walk_title_values` ignore les objets imbriqués sous une clé `title` — étendre les deux marcheurs.
  - `[medium]` `[patch]` `_prefer_full_title` accepte un snippet sous-chaîne d'un titre validé mentionné plus tard sur la même ligne — n'autoriser la substitution que lorsque le snippet est un préfixe unique du titre complet.
  - `[medium]` `[patch]` La détection d'un titre non validé utilise une sous-chaîne brute — exiger une correspondance sur frontières de mot pour éviter les faux rejets.
  - `[medium]` `[patch]` `version = int(...)` laisse échapper une `ValueError` brute — envelopper en `ReportGenerationFailedException`.
  - `[low]` `[patch]` Aucun test de compilation avec des sections permutées — ajouter `test_compile_report_canonicalizes_permuted_sections` et vérifier l'ordre canonique des deux formats et des empreintes.
  - `[low]` `[patch]` Le SQL offline de la migration n'affirme pas `ON DELETE CASCADE` sur `reports.case_id` — ajouter l'assertion.
  - `[deferred]` `[defer]` Deux aperçus concurrents écrivant des jetons divergents — déjà consigné dans le frontmatter `deferred`.
  - `[deferred]` `[defer]` Aucun test d'affinité de boucle avec un vrai `UnifiedLLMClient` — déjà consigné dans le frontmatter `deferred`.
  - `[false]` `[reject]` Un drapeau local périmé effacé lors d'une approbation exposerait une reprise externe — l'approbation explicite est la source de vérité ; arbitrage boucle 3 conservé.
  - `[false]` `[reject]` `sprint-status.yaml` resterait `backlog` — finalisation volontairement différée après convergence, appliquée à la clôture.
  - `[false]` `[reject]` Le format brut de `update_report` pourrait ne pas correspondre à la ligne — une ligne `draft` reste libre ; seule la promotion est réservée à `generate_report`.
  - `[false]` `[reject]` Les titres validés pseudonymisés seraient envoyés en clair — le pseudonymiseur partagé transforme les entités reconnues ; lecture arbitrée et testée.
  - `[false]` `[reject]` `internal=user_id is None` autoriserait un accès sans utilisateur — contrat de service explicite, déjà arbitré.
  - `[false]` `[reject]` `**formats` ajouterait des clés de premier niveau non déclarées — les clés sont imbriquées dans `report` ; arbitrage répété.
  - `[false]` `[reject]` Un titre non validé sans indice textuel serait scellé — la boucle 2 définit précisément les formes détectables ; lecture arbitrée (signaux doublonnés).
  - `[false]` `[reject]` Un jeton corrompu bloquerait un refus H3 — le refus emprunte le chemin `reporting` et la continuité du jeton y est exigée ; lecture arbitrée.
  - `[false]` `[reject]` Les noms de contraintes ORM divergeraient de la migration — les paramètres parametrizés sont exactement `ck_reports_*`.
  - `[false]` `[reject]` `arbitrate_gate_h3` n'aurait pas de test de jeton corrompu au refus — même lecture arbitrée.
  - `[false]` `[reject]` Le verrou de ligne pendant l'appel LLM — déjà consigné dans le frontmatter `deferred`.
- Note d'implémentation (sans nouveau signal de revue) : `_clean_candidate` ignore désormais les fragments uniquement ponctuatifs, après qu'un faux positif `{},` détecté dans le JSON rendu ait fait échouer `test_update_report_structured_metadata_agrees_with_the_row` lors de la validation du patch.

### 2026-11-26 — Review pass (clôture)
- verdicts: 17 signaux (10 blind hunter, 6 edge cases, 1 verification gap, 0 intent gap) — aucun `bad_spec`, aucun `intent_gap`. Routing après dédoublonnage : 6 `patch`, 4 `defer`, 5 `reject` (dont 2 doublons consignés). Détail : high 1, medium 3, low 2, deferred 4, false 5, doublons 2.
- findings retenus (`patch`, racines vérifiées dans le code) :
  - `[high]` `[patch]` `gate_h3_node` teste encore `state.get("h3_approved")` par vérité brute : une chaîne `"false"` devient `h3_approved=True` avant d'atteindre la garde stricte de `reporting_node` ; utiliser `verdict_flag` pour les deux verdicts et ajouter le test de non-promotion.
  - `[medium]` `[patch]` Le spec (ligne 146) impose `REPORT_GENERATION_FAILED` pour un `case_id` mal formé, mais le dernier patch a fait remonter `ValidationException` (422) : restaurer l'enveloppement typé avec log sans la valeur brute, tout en gardant la remontée 422 pour un dossier valide mais absent.
  - `[medium]` `[patch]` `_mentions_title` compare encore les titres exclus par sous-chaîne brute : un titre proposé inclus dans un titre validé rejette à tort la génération ; exiger une correspondance sur frontières de mot et ignorer les occurrences couvertes par un titre validé.
  - `[medium]` `[patch]` `generate_sync` ne capture que `TimeoutError` : toute autre erreur du worker (et un `RuntimeError` de `submit` si l'exécuteur est fermé) échappe sans code typé ; envelopper ces deux chemins en `REPORT_GENERATION_FAILED`.
  - `[low]` `[patch]` Le `CHECK` hexadécimal de `audit_events.payload_sha256` n'est vérifié que dans le SQL de migration — ajouter un test d'insertion rejetée.
  - `[low]` `[patch]` La criticité variée des constats validés n'est pas couverte — ajouter une fixture avec deux sévérités distinctes et vérifier leur présence dans les deux formats.
  - `[deferred]` `[defer]` Annulation coopérative avant l'appel LLM après dépassement du délai — demanderait un protocole d'annulation coopérative dans la rédaction externe, hors périmètre.
  - `[deferred]` `[defer]` Course réelle entre deux sessions sur `(case_id, version, format)` — le test séquentiel de conflit et le test de contrainte d'unicité couvrent le mécanisme ; un test threadé reste reporté.
  - `[deferred]` `[defer]` Mutation du store de pseudonymisation avant la persistance du jeton — déjà consigné dans le frontmatter `deferred`.
  - `[deferred]` `[defer]` Statut `status: 'in-review'` et story `backlog` — finalisation appliquée à la clôture, pas sous revue.
  - `[false]` `[reject]` Les clés de dictionnaire du prompt externe ne seraient pas masquées — les clés proviennent de `model_dump()` (noms de champs fixes) ; seules les valeurs libres sont pseudonymisées.
  - `[false]` `[reject]` UUID, horodatages et nombres traverseraient le LLM en clair — identifiants et métadonnées temporelles ne sont pas des données textuelles libres ; `case_id` est exigé par le contrat.
  - `[false]` `[reject]` `ReportStatus(str(status))` et `ReportContent.model_validate` laisseraient remonter des erreurs brutes — elles traversent le chemin d'échec typé `REPORT_GENERATION_FAILED` prévu par le contrat.
  - `[false]` `[reject]` `list_reports` renverrait une liste vide pour un dossier inexistant en mode interne — comportement de lecture cloisonnée cohérent, aucun `CASE_NOT_FOUND` exigé pour une liste.
  - `[false]` `[reject]` `ReportSection.order` serait ignoré par le compilateur — l'ordre canonique est la règle du contrat ; l'accepter depuis l'appelant contredirait la sérialisation déterministe.
  - `[false]` `[reject]` (doublon) `_mentions_title` par sous-chaîne — déjà retenu et patché ci-dessus.
  - `[false]` `[reject]` (doublon) identifiant mal formé remonté en 422 — déjà retenu et patché ci-dessus.

### 2026-11-26 — Review pass (confirmation après clôture)
- verdicts: 17 signaux (12 blind hunter, 2 verification gap, 3 edge cases) — aucun `bad_spec`, aucun `intent_gap`. Routing : 6 `patch`, 4 `defer`, 7 `reject` (dont 2 doublons). Détail : high 1, medium 1, low 4, deferred 4, false 5, doublons 2.
- findings retenus (`patch`, racines vérifiées dans le code) :
  - `[high]` `[patch]` Le patch précédent a remplacé la vérité brute de `gate_h3_node` par `verdict_flag`, qui promeut aussi `"true"`, `"1"`, `"yes"` et `"oui"` en `h3_approved=True` littéral : la chaîne contourne la garde stricte du nœud ; n'accepter que `state.get("h3_approved") is True` à la porte, garder `verdict_flag` pour le refus, et tester toutes les formes affirmatives non booléennes à la porte et au nœud.
  - `[medium]` `[patch]` `reporting_node` choisit `case_id` depuis l'état ou le contexte sans contrôle de cohérence — une divergence produirait un rapport scellé avec le jeton d'un autre dossier ; rejeter avec `REPORT_GENERATION_FAILED`.
  - `[low]` `[patch]` Le repli de `_json_type()` dans la migration 009 force `postgresql` quandaucun dialecte n'est détectable — utiliser un dialecte générique pour ne pas émettre JSONB sur SQLite.
  - `[low]` `[patch]` Ajouter un test paramétré du garde-fou `status` de `generate_report` (`draft`, `exported`, `validated`).
  - `[low]` `[patch]` Ajouter une assertion explicite que les empreintes Markdown et JSON sont distinctes.
  - `[low]` `[patch]` Reconcilier le frontmatter `deferred` avec les reports consignés et documenter pourquoi `review_loop_iteration` reste figé à 3 (aucun `bad_spec` depuis la boucle 3).
  - `[deferred]` `[defer]` Nettoyage complet des clés transitoires du runtime context — changement plus large dans l'orchestrateur ; seul `llm_client` est nettoyé aujourd'hui.
  - `[deferred]` `[defer]` Contrôle de continuité du jeton dans `ReportService` — déjà arbitré : la continuité est imposée à la frontière d'orchestration.
  - `[deferred]` `[defer]` Bornes sur la taille du prompt externe — absent du contrat Story 8.3.
  - `[deferred]` `[defer]` Pagination de `list_reports` — hors périmètre du contrat.
  - `[false]` `[reject]` Un titre inventé sans indice textuel serait scellé — lecture arbitrée depuis la boucle 2 (signaux doublonnés).
  - `[false]` `[reject]` Un appelant direct de l'agent pourrait injecter des faits non validés — contrat de couche : l'agent reçoit des faits déjà filtrés par le service.
  - `[false]` `[reject]` Un appelant interne pourrait passer `h3_approved=True` — contrat de service explicite, déjà arbitré.
  - `[false]` `[reject]` Aucun producteur de lignes `draft` n'existe — l'API `draft` est prévue pour les producteurs futurs ; lecture arbitrée.
  - `[false]` `[reject]` Statut et story resteraient `in-review`/`backlog` — finalisation appliquée à la clôture, pas sous revue.
  - `[false]` `[reject]` (doublon) promotion de chaînes affirmatives à la porte H3 — déjà retenu et patché ci-dessus.
  - `[false]` `[reject]` (doublon) garde de statut non testée — déjà retenue et patchée ci-dessus.

### 2026-11-26 — Revue ciblée finale
- Convergence confirmée — aucun nouveau finding bloquant. La porte H3 n'accepte que `h3_approved is True`, la divergence de `case_id` est rejetée avant tout accès DB, les nouveaux tests échouent si leur garde est retirée, et le repli de `_json_type()` préserve les chemins PostgreSQL et SQLite.

## Auto Run Result

Status: done. `followup_review_recommended: true` — la passe de confirmation a patché un finding `high` (promotion de chaînes affirmatives en approbation H3 littérale) ; la revue ciblée qui a suivi n'a relevé aucun nouveau blocage.

**Résumé** : la Story 8.3 est implémentée. `reporting_node` reste un adaptateur qui valide la porte H3, résout les dépendances d'exécution et délègue à `ReportService`. La génération produit deux lignes `Report` `validated` (Markdown et JSON) regroupées par `generation_id`, scellées par une empreinte SHA-256 calculée sur les octets UTF-8 exacts persistés. Le mode externe exige une approbation booléenne littérale, un pseudonymiseur injecté et un client configuré pour le rôle `RAPPORTEUR` ; un refus ou `local_report_mode` force le gabarit local sans appel réseau. Les lectures sont cloisonnées par `case_id` et autorisées par dossier, la régénération crée une génération distincte sans toucher aux lignes antérieures, et toute erreur est exposée avec le code `REPORT_GENERATION_FAILED`. La table `audit_events` est créée dans la migration `009` avec l'ORM correspondant, sans service ni trigger d'audit (Story 8.5). Aucun endpoint 8.4 ni PDF n'a été ajouté.

**Fichiers principaux** : `backend/migrations/versions/009_create_report_and_audit_tables.py` ; `backend/src/iryx/reporting/{models,schemas,compiler,verdicts,services,rapporteur_agent}.py` ; `backend/src/iryx/audit/models.py` ; `backend/src/iryx/orchestrator/{graph,services,router}.py` ; `backend/src/iryx/core/exceptions.py` ; suites de tests unitaires dédiées dans `backend/tests/unit/`.

**Vérifications finales** (depuis `backend`) :
- `uv run pytest -q` → `1026 passed in 63.35s`
- `uv run ruff check src tests` → `All checks passed!`
- `uv run pytest -q tests/unit/test_alembic.py tests/unit/test_report_migration.py` → `15 passed in 3.25s`

**Revue** : itérations successives de correctifs sans `bad_spec` ni `intent_gap` depuis la boucle 3 ; le compteur `review_loop_iteration` reste donc figé à 3. Les divergences d'alignment (service en couches, statut DB des constats, exception typée au lieu d'un endpoint, `local_report_mode` comme verdict local) ont été arbitrées et consignées. Les éléments non traités sont enregistrés dans le frontmatter `deferred`, notamment l'affinité de boucle du client LLM asynchrone, la course sur le jeton de pseudonymisation, le verrou de ligne pendant la rédaction, le nettoyage du runtime context et les limites de taille du prompt. Les risques résiduels connus sont le DDL PostgreSQL non exécuté sur un serveur réel et l'absence de test d'affinité avec un vrai `UnifiedLLMClient`.

**Clôture** : spec passée en `done`, story 8-3 passée en `done` dans `sprint-status.yaml`, commit effectué sans push.
