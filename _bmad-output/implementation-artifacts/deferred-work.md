
- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-service-authentification-jwt-endpoint-connexion-api.md`
  summary: Durcissement de la valeur par défaut de jwt_secret_key en environnement de production.
  evidence: Dans core/config.py, jwt_secret_key possède une valeur par défaut de développement issue de Story 1.1; un validateur interdisant cette clé par défaut hors environnement de développement devra être intégré lors du durcissement transversal.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-service-authentification-jwt-endpoint-connexion-api.md`
  summary: Synchronisation documentaire de docs/adr/ADR-0006 avec la durée d'expiration de 60 minutes et le contrôle SQL de get_current_user.
  evidence: L'ADR-0006 initial mentionnait 480 minutes et l'absence de requête SQL, alors que Story 1.4 a retenu 3600 secondes et une vérification de l'état actif en base de données.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-analyseur-de-journaux-d-evenements-windows-evtx-python-evtx.md`
  summary: Ajouter une fixture EVTX binaire réelle (Security.evtx avec enregistrements 4624/4625) pour tester le parsing de bout en bout sans mock de python-evtx.
  evidence: Tous les tests d'extraction d'enregistrements mockent Evtx.Evtx ; seul le fichier vide exerce la vraie bibliothèque, donc les écarts entre mock et vrais objets Record ne seraient pas détectés.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-5-analyseur-d-artefacts-d-execution-windows-prefetch-dissect.md`
  summary: Ajouter une fixture Prefetch binaire compressée MAM réelle pour tester la décompression de bout en bout sans mock de dissect.util.lzxpress_huffman.
  evidence: Les tests unitaires actuels mockent lzxpress_huffman.decompress pour simuler des données SCCA valides; intégrer un fichier .pf Windows 10 réel exercera le décodage LZ-Xpress natif en conditions réelles.

- source_spec: `D:\MY_PROEJCT\IRYX\_bmad-output\implementation-artifacts\spec-7-1-service-reconstruction-correlation-chronologie-utc.md`
  summary: Implémentation du streaming de résultats et de la pagination pour les requêtes volumineuses de timeline.
  evidence: Dans TimelineService.get_timeline_projection, l'ensemble des observations du dossier est chargé en mémoire d'un bloc via .all(); la pagination (limit, offset) et le filtrage temporel sont explicitement prévus et isolés dans la Story 7.2 (NFR-PERF-07).

- source_spec: `D:\MY_PROEJCT\IRYX\_bmad-output\implementation-artifacts\spec-7-1-service-reconstruction-correlation-chronologie-utc.md`
  summary: Création d'un index composite relationnel sur (case_id, timestamp_utc) pour la table observations via migration Alembic.
  evidence: La table observations possède des index séparés sur case_id et timestamp_utc; l'ajout d'un index composite accélérera les tris chronologiques ordonnés par dossier lors de l'implémentation de l'API de consultation paginée (Story 7.2).
