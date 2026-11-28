
- source_spec: `_bmad-output/implementation-artifacts/spec-4-3-analyseur-de-journaux-d-evenements-windows-evtx-python-evtx.md`
  summary: Ajouter une fixture EVTX binaire réelle (Security.evtx avec enregistrements 4624/4625) pour tester le parsing de bout en bout sans mock de python-evtx.
  evidence: Tous les tests d'extraction d'enregistrements mockent Evtx.Evtx ; seul le fichier vide exerce la vraie bibliothèque, donc les écarts entre mock et vrais objets Record ne seraient pas détectés.

- source_spec: `_bmad-output/implementation-artifacts/spec-4-5-analyseur-d-artefacts-d-execution-windows-prefetch-dissect.md`
  summary: Ajouter une fixture Prefetch binaire compressée MAM réelle pour tester la décompression de bout en bout sans mock de dissect.util.lzxpress_huffman.
  evidence: Les tests unitaires actuels mockent lzxpress_huffman.decompress pour simuler des données SCCA valides; intégrer un fichier .pf Windows 10 réel exercera le décodage LZ-Xpress natif en conditions réelles.

- source_spec: `_bmad-output/implementation-artifacts/spec-8-4-endpoints-de-consultation-et-telechargement-des-rapports-scelles.md`
  summary: Revenir sur le changement `fastapi` → `fastapi[standard]` et le churn de `uv.lock` une fois la story 8.4 terminée, si ces dépendances ne sont plus nécessaires.
  evidence: Modifications présentes dans l’arbre avant l’implémentation de la story et explicitement conservées à la demande de l’utilisateur ; elles ne sont pas causées par cette story et ne doivent pas être annulées ici.

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-dockerfile-multi-etapes-et-docker-compose-mono-serveur.md`
  summary: Refuser en production les valeurs placeholders de SECRET_KEY et POSTGRES_PASSWORD copiées depuis .env.example.
  evidence: Comportement préexistant de core/config.py (seul JWT_SECRET_KEY est gardé en production) ; le correctif exigerait de modifier backend/src, interdit par le bloc gelé de la story 9.1.

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-dockerfile-multi-etapes-et-docker-compose-mono-serveur.md`
  summary: Documenter la procédure de recréation de postgres_data lorsque POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB changent après l'initialisation du volume.
  evidence: L'image PostgreSQL officielle n'applique ces variables qu'à un volume vide ; l'API tente alors de se connecter avec des identifiants inconnus. Comportement préexistant de l'image, non causé par la story 9.1.

- source_spec: `_bmad-output/implementation-artifacts/spec-9-1-dockerfile-multi-etapes-et-docker-compose-mono-serveur.md`
  summary: Borner alembic upgrade head dans l'entrypoint API pour eviter un blocage indefini sur un verrou de migration.
  evidence: Un verrou database peut bloquer la migration sans jamais la faire échouer ; la matrice gelée couvre l'échec de migration mais pas ce blocage, et ajouter `timeout` + `MIGRATION_TIMEOUT_SECONDS` crée une surface nouvelle non démontrée dans cette exécution.

- source_spec: _bmad-output/implementation-artifacts/spec-9-2-durcissement-securite-conteneur-traitement-isolation-reseau.md
  summary: Fournir une migration ou une procédure pour rendre les preuves scellées de l'ancien volume evidence_data visibles après le passage au montage séparé brut :ro / staging.
  evidence: Le déplacement de evidence_data vers /data/evidence/raw:ro rend invisibles les fichiers /data/evidence/staging/<id>.bin déjà scellés ; aucun test ni helper d'upgrade ne couvre ce cas et le montage :ro interdit la réparation in place. Limite déjà consignée comme connue, sans volume préexistant observé.

- source_spec: `_bmad-output/implementation-artifacts/spec-9-3-script-peuplement-demonstration-seed-data-incident-windows.md`
  summary: Ajouter unicité DB `Organization.name`, `Case(organization_id, title)`, `Evidence(case_id, original_name)` et verrouillage/transaction pour rendre le seed concurrent-safe.
  evidence: `_ensure_organization`/`_ensure_case`/`_ensure_evidence` sont check-then-insert sans `INSERT … ON CONFLICT`, advisory lock, ni contraintes `UNIQUE` sur ces tables ; deux exécutions concurrentes ou des doublons préexistants peuvent créer des doublons métier. Correctif hors `backend/src/iryx/scripts/**`.