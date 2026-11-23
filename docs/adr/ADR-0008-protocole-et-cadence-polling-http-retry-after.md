# ADR-0008 : Protocole et cadence de consultation asynchrone par polling HTTP

- **Date** : 2026-11-23
- **Statut** : acceptée

---

## Contexte

La décision D-24 fixe le polling HTTP REST comme unique mécanisme de suivi en temps réel pour le MVP (rejetant formellement WebSockets et SSE). Les conventions de développement (`docs/05-conventions-backend.md`) imposent l'émission du code HTTP 202 Accepted pour toute opération longue (> 500 ms) telle que l'ingestion de preuve ou l'exécution d'un outil forensique.

Toutefois, en l'absence de contrat d'en-tête explicite, un client pourrait surcharger le serveur en interrogeant l'API sans temporisation.

---

## Décision

Nous retenons l'**Option A** :
1. Normalisation systématique de l'en-tête HTTP standard `Retry-After: 3` (3 secondes) sur l'ensemble des réponses HTTP 202 Accepted émises par le back-end IRYX.
2. Format de réponse JSON uniforme pour toute tâche asynchrone :
   ```json
   {
     "task_id": "uuid-str",
     "status": "pending | processing | completed | failed",
     "progress": 0.0,
     "poll_url": "/api/v1/cases/{case_id}/tasks/{task_id}"
   }
   ```
3. Cadence de polling conseillée pour l'interface consommatrice : 3 à 5 secondes, avec obligation de mettre en œuvre un recul exponentiel (*exponential backoff*) plafonné en cas d'erreur de transport HTTP.

---

## Conséquences

### Positives
- **Conformité aux standards Web** : Respect strict du standard RFC 9110 concernant la gestion du code HTTP 202 et de l'en-tête `Retry-After`.
- **Protection de l'infrastructure** : Élimination des risques d'attaques par déni de service involontaire (boucles de requêtes intensives).
- **Contrat clair pour le front-end** : Schéma prédictible pour l'ensemble des opérations asynchrones.

### Négatives / Risques
- Exige une rigueur constante des développeurs lors de la création de nouveaux contrôleurs de tâches asynchrones.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & AI/Tech Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
