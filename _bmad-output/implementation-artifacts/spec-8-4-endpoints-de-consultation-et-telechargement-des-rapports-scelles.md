---
title: 'Story 8.4 : Endpoints de consultation et téléchargement des rapports scellés'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: 'c0c7a199fdc717444ffdc995be9996b4dab2ecde'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les rapports scellés de la Story 8.3 sont persistés, mais aucun endpoint ne permet de les consulter ni de récupérer le livrable officiel avec son empreinte.

**Approach:** Exposer deux `GET` cloisonnés par dossier : consultation des rapports et téléchargement du contenu stocké avec `X-Report-SHA256` et un `Content-Type` adapté.

## Boundaries & Constraints

**Always:** Passer par `verify_case_access` avec l’utilisateur authentifié ; refuser tout appel sans `user_id`. Servir les octets exactement persistés, sans recompilation ni recalcul. Filtrer `report_id` et `case_id` ensemble : un rapport étranger est indiscernable d’un rapport absent. N’exposer que les rapports `validated`. Valider les UUID avant toute lecture.

**Never:** Aucun `internal=True` depuis un endpoint public, aucune génération, modification de contenu, suppression, PDF, écriture d’audit ni mutation de statut. Le téléchargement reste en lecture seule. Aucune dérogation aux invariants H3 et de scellement de la Story 8.3.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Consultation nominale | Membre, rapports `validated` présents | HTTP 200 ; enveloppe paginée ; `id`, `format`, `status`, `sha256` visibles ; rien d’un autre dossier | N/A |
| Téléchargement nominal | Membre, rapport `validated` autorisé | HTTP 200 ; corps identique à `Report.content` ; en-tête égal à `Report.sha256` | N/A |
| Rapport absent, étranger ou non `validated` | `report_id` hors du dossier ou non scellé | HTTP 404, code `REPORT_NOT_FOUND` | Exception typée |
| Non-membre | Aucune appartenance à l’organisation | HTTP 403 | `INSUFFICIENT_PERMISSIONS` |
| Dossier inconnu | `case_id` absent | HTTP 404 | `CASE_NOT_FOUND` |
| UUID invalide | `case_id` ou `report_id` mal formé | HTTP 422 | `INVALID_UUID` |
| Format invalide | `format=pdf` | HTTP 422 | `INVALID_REPORT_FORMAT` |

## Decisions

- Seuls les rapports `validated` sont consultables et téléchargeables ; `draft` et `exported` restent exclus.
- La liste renvoie `{items,total,total_items,limit,offset,has_more}` avec `limit` (défaut 50, max 100) et `offset` (défaut 0).
- Le téléchargement ne modifie aucun statut : pas de passage à `exported`, aucun `UPDATE`.

</frozen-after-approval>

## Code Map

- `backend/src/iryx/reporting/models.py:71-120` -- ORM `Report`, formats, statuts, unicité `(case_id,version,format)`.
- `backend/src/iryx/reporting/schemas.py:36-48,190-218` -- `ReportFormat`, `ReportStatus`, `ReportOut` (contient `content` et `sha256`) ; y ajouter l’enveloppe paginée.
- `backend/src/iryx/reporting/services.py:484-521` -- `list_reports`, filtre `format`, tri, autorisation ; étendre pour la pagination et le filtre `validated`.
- `backend/src/iryx/reporting/services.py:36-47,78-117,626-639` -- `_safe_uuid`, `_authorize`, `to_out` ; réutiliser sans `internal`.
- `backend/src/iryx/reporting/services.py` -- ajouter la lecture unitaire filtrée par `(case_id, report_id)`, `validated` et utilisateur.
- `backend/src/iryx/reporting/compiler.py:35-37,96-103` -- `sha256_text` ; ne pas recalculer le contenu servi.
- `backend/src/iryx/core/exceptions.py:49-77,620-639` -- erreurs typées et enveloppe JSON ; `REPORT_NOT_FOUND` manquant.
- `backend/src/iryx/cases/dependencies.py:21-46` -- `verify_case_access` : 404 dossier, 403 non-membre.
- `backend/src/iryx/evidence/router.py:37-61,90-121` -- patrons d’en-tête et de liste paginée.
- `backend/src/iryx/main.py:85-92` -- enregistrement des routers.
- `backend/tests/conftest.py:35-118` et `backend/tests/integration/test_findings_api.py:24-76` -- fixtures DB/JWT et création dossier.
- `backend/tests/unit/test_report_service.py:215-239,482-517` -- création de rapports validés et tests d’autorisation.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/core/exceptions.py` -- ajouter l’exception 404 `REPORT_NOT_FOUND`.
- [x] `backend/src/iryx/reporting/services.py` -- filtrer la liste sur `validated`, ajouter la pagination et la lecture unitaire cloisonnée avec UUID et 404.
- [x] `backend/src/iryx/reporting/schemas.py` -- ajouter l’enveloppe paginée de `ReportOut`.
- [x] `backend/src/iryx/reporting/router.py` -- créer les deux `GET` avec `verify_case_access`, `get_current_user`, `get_db`, `limit`/`offset`, le contenu stocké, l’en-tête et le MIME exacts, sans mutation.
- [x] `backend/src/iryx/main.py` -- enregistrer le router reporting.
- [x] `backend/tests/integration/test_reports_api.py` -- couvrir la matrice, la pagination, deux dossiers et les en-têtes.
- [x] `backend/tests/unit/test_report_service.py` -- tester lecture unitaire, filtre `validated`, 404 et absence de contournement `internal`.

**Acceptance Criteria:**
- Given un membre, when il consulte la liste, then seuls les rapports `validated` du dossier apparaissent dans l’enveloppe paginée et dans un ordre déterministe.
- Given un rapport `validated` autorisé, when il est téléchargé, then le corps est bit à bit identique à `Report.content`, l’en-tête vaut `Report.sha256` et aucun statut n’est modifié.
- Given `markdown` ou `json`, when le rapport est téléchargé, then le `Content-Type` est `text/markdown` ou `application/json`.
- Given un rapport `draft`, `exported` ou d’un autre dossier, when il est demandé, then la réponse est 404 `REPORT_NOT_FOUND` sans fuite de contenu.
- Given un non-membre, when il appelle un endpoint, then la réponse est 403 avant toute lecture de rapport.
- Given l’application démarrée, when OpenAPI est inspecté, then les deux chemins de la story sont présents.

## Implementation Notes

Revue indépendante : 21 findings triés, 5 groupes corrigés en auto-fix, 1 élément préexistant différé (`fastapi[standard]` / `uv.lock`, conservé à la demande de l’utilisateur), les autres rejetés sur preuve.

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence et route |
|---|---------|---------|-------------------|
| B1 | `backend/pyproject.toml`, `uv.lock` — `fastapi[standard]` et dépendances sans rapport | `[low]` | Modifications présentes avant la story et conservées sur demande explicite ; `defer` (préexistant, hors portée). |
| B2 | `reporting/schemas.py:191` — la liste renvoie `ReportOut.content` au lieu d’un schéma métadonnées | `[false]` | Le contrat figé exige les champs visibles sans exclure `content`, et le Code Map cite explicitement `ReportOut` avec `content` ; seules des lignes `validated` du dossier autorisé sont renvoyées. Rejeté. |
| B3 | `reporting/router.py:118-124` — pas de `Content-Disposition` au téléchargement | `[false]` | Le contrat figé porte sur le corps exact, `X-Report-SHA256` et le MIME ; aucun nom de fichier n’est promis et le client API choisit son nom. Rejeté. |
| B4 | `reporting/router.py:118-124` — pas de `Cache-Control: no-store` | `[false]` | Les réponses exigeant `Authorization` ne peuvent pas être stockées par un cache partagé par défaut, et aucun comportement de cache n’est spécifié ; aucun débordement multi-utilisateur démontré. Rejeté. |
| B5 | `reporting/router.py:88-97` — OpenAPI ne documente ni l’en-tête ni le type du téléchargement | `[medium]` | Vérifié sur `create_app().openapi()` : la réponse 200 du download ne contient ni `content` ni `headers` alors que l’empreinte est centrale au contrat. Route `patch` avec B13. |
| B6 | `reporting/router.py:53-56` — `format` déclaré `str` sans enum OpenAPI | `[false]` | Une enum ou un pattern ferait échouer la validation avant le service et remplacerait le code exigé `INVALID_REPORT_FORMAT` par `VALIDATION_ERROR` ; le typage actuel préserve le contrat. Rejeté. |
| B7 | `reporting/router.py:25-35,66-77` — contrôle d’accès répété trois fois par requête liste | `[low]` | Les deux couches (`verify_case_access` et `_authorize` avec `user_id`) sont imposées par le bloc figé ; la fenêtre d’incohérence supposerait une mutation concurrente d’appartenance non démontrée, et retirer un garde-fou n’est pas une correction directe. Rejeté. |
| B8 | `reporting/router.py:66-84` — `total` et `items` issus de deux requêtes indépendantes | `[low]` | Aucune écriture concurrente de rapport n’est démontrée dans ce chemin ; corriger exigerait une stratégie de snapshot ou de fenêtre unique, plus complexe qu’une correction directe. Groupé avec E2, rejeté. |
| B9 | `reporting/services.py:533-534` — `offset` ignoré si `limit` est absent | `[medium]` | Confirmé : `.offset(offset)` n’est appliqué que dans `if limit is not None`, donc un appel direct avec `offset>0` renvoie la première page. Groupé avec E1, route `patch`. |
| B10 | `reporting/router.py:113-116` — branche MIME invalide masque une corruption comme 404 | `[maybe-false]` | La contrainte DB limite `format` à `markdown|json` ; aucun chemin démontré ne produit une valeur invalide sur une ligne `validated`. Si le cas survenait, l’impact serait faible ; rejeté avec cette réserve. |
| B11 | `backend/tests/integration/test_reports_api.py` — aucun test 401 sans jeton | `[low]` | Confirmé : les nouveaux endpoints n’ont pas de cas non authentifié alors que l’authentification est une frontière du contrat. L’ajout de test est une correction directe ; route `patch`. |
| B12 | `backend/tests/integration/test_reports_api.py:192-222` — bornes de pagination et filtre `json` non vérifiés | `[medium]` | Finding pré-vérifié par la couche verification-gap : seuls `limit=1` et les valeurs par défaut sont exercés ; sans `ge/le`, une régression produirait 500 ou une page non bornée. Groupé avec VG1, route `patch`. |
| B13 | `backend/tests/integration/test_reports_api.py:182-189` — test OpenAPI limité à la présence des chemins | `[low]` | Confirmé : aucune assertion sur le schéma d’enveloppe, les paramètres ou les en-têtes de téléchargement. Groupé avec B5, route `patch`. |
| B14 | `backend/tests/integration/test_reports_api.py:788-812` — assertion de contenu tautologique | `[medium]` | Confirmé : `expire_all()`/`refresh(report)` agit sur le même objet que `reports_setup[report_key]`, donc la comparaison ne vérifie rien. Route `patch`. |
| B15 | Spec et sprint-status en retard sur l’état du workflow | `[false]` | Le diff avait été généré avant le passage de la spec à `in-review`, déjà appliqué ; les sections de suivi sont gérées par les étapes suivantes, et toute correction proposée consisterait à éditer la spec. Rejeté. |
| B16 | `test_reports_api.py` — aucune assertion sur les chaînes de contenus étrangers dans la liste | `[false]` | Les tests comparent déjà l’ensemble des `id`, `total`, `status` et `case_id`, ce qui exclut toute ligne `draft`, `exported` ou étrangère ; aucune fuite de contenu n’est possible sans casser ces assertions. Rejeté. |
| B17 | `reporting/schemas.py:234-242` — validateur `total_items` seulement pour `dict` | `[false]` | Le router est l’unique appelant et fournit toujours `total_items` ; aucun appelant avec un objet attribut n’existe, donc le comportement décrit n’est pas atteignable. Rejeté. |
| E1 | `reporting/services.py:510-535` — pagination invalide ou `offset` sans `limit` | `[medium]` | Confirmé par lecture du service : ni `offset<0` ni `limit<1` n’est rejeté, et `offset` est ignoré sans `limit`. Groupé avec B9, route `patch`. |
| E2 | `reporting/router.py:66-84` — métadonnées de pagination incohérentes si les lignes changent | `[low]` | Même cause que B8 ; la contradiction suppose une mutation concurrente non démontrée et la correction demandée ajoute une stratégie de snapshot. Rejeté. |
| E3 | `reporting/schemas.py:222-242` — `total_items`/`has_more` non validés | `[false]` | Ces champs sont construits par le router à partir de `total`, `limit`, `offset` et `items` ; aucune entrée externe ne peut les rendre incohérents. Rejeté. |
| VG1 | `reporting/router.py:57-61` — bornes `limit`/`offset` non couvertes par un test | `[medium]` | Finding pré-vérifié : `test_evidence_api.py:780-797` montre le patron attendu (422 `VALIDATION_ERROR`) mais l’endpoint rapports n’est testé qu’avec des valeurs valides. Groupé avec B12, route `patch`. |

## Verification

**Commands:**
- `cd backend && uv run pytest -q` -- result: 1058 passed in 86.23s.
- `cd backend && uv run ruff check src tests` -- result: `All checks passed!`.
- `cd backend && uv run pytest -q tests/integration/test_reports_api.py tests/unit/test_report_service.py` -- result: 74 passed in 7.91s.
