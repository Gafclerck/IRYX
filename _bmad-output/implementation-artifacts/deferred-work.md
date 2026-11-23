
- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-service-authentification-jwt-endpoint-connexion-api.md`
  summary: Durcissement de la valeur par défaut de jwt_secret_key en environnement de production.
  evidence: Dans core/config.py, jwt_secret_key possède une valeur par défaut de développement issue de Story 1.1; un validateur interdisant cette clé par défaut hors environnement de développement devra être intégré lors du durcissement transversal.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-service-authentification-jwt-endpoint-connexion-api.md`
  summary: Synchronisation documentaire de docs/adr/ADR-0006 avec la durée d'expiration de 60 minutes et le contrôle SQL de get_current_user.
  evidence: L'ADR-0006 initial mentionnait 480 minutes et l'absence de requête SQL, alors que Story 1.4 a retenu 3600 secondes et une vérification de l'état actif en base de données.
