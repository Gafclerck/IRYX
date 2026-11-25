# ADR-0011 : Transport de l'authentification et gestion de session sans état (Stateless)

- **Date** : 2026-11-25
- **Statut** : acceptée
- **Numérotation** : Numérotée ADR-0011 (premier numéro libre à la suite des ADR-0001 à ADR-0010 du back-end).

---

## 1. Contexte

La décision d'architecture initiale D-43 préconisait un transport de jeton d'accès encapsulé dans un cookie `httpOnly` avec en-tête anti-CSRF. Cependant, l'intégration de l'interface front-end React requiert l'usage du standard `Authorization: Bearer` pour les requêtes d'API de données, tout en assurant le maintien de la session de l'analyste lors du rafraîchissement d'un onglet de navigateur.

L'ADR-0006 du back-end avait acté une approche strictement sans état (*stateless*) avec un jeton d'accès unique d'une durée de 8 heures sans jeton de renouvellement. Pour concilier sécurité contre les failles XSS, simplicité d'infrastructure et maintien de session, le modèle de transport d'authentification a été révisé selon les décisions validées D1, D3, D5 et D6.

---

## 2. Décisions validées (D1, D3, D6)

1. **Jeton d'accès (Access Token) - Décision D3** :
   - Durée de validité arrêtée à **15 minutes** (borne basse validée).
   - Transmis à chaque requête d'API de données via l'en-tête HTTP standard `Authorization: Bearer <token>`.
   - Détenu exclusivement en mémoire vive volatile de l'application cliente (état React / TanStack Query).
   - Formellement interdit de tout stockage persistant dans le navigateur : aucun enregistrement dans `localStorage` ni dans `sessionStorage`.

2. **Jeton de renouvellement (Refresh Token) - Décisions D1, D3, D6** :
   - **Mode de transport (D1)** : Délivré par le serveur lors de la connexion sous forme d'un cookie HTTP doté des attributs de protection : `httpOnly`, `Secure`, `SameSite=Strict`.
   - **Portée du cookie (D1)** : Chemin strictement limité à l'endpoint de renouvellement (`Path=/api/auth/refresh`).
   - **Durée de validité (D3)** : Arrêtée à **7 jours**.
   - **Architecture sans état (D6)** : Jeton de renouvellement *stateless simple*, signé cryptographiquement par le serveur (secret JWT), sans enregistrement dans une table de base de données, sans rotation à chaque usage et sans détection de réutilisation.
   - **Déconnexion (D6)** : L'action de déconnexion efface le cookie côté navigateur. Elle ne révoque pas le jeton côté serveur (absence de liste de révocation ou de table d'état).

---

## 3. Risques acceptés et limites du modèle sans état (D6)

Le choix d'un modèle sans état pour le refresh token simplifie l'architecture mais comporte des limites opérationnelles expressément acceptées :

1. **Absence de rotation unitaire** :
   Le même refresh token reste valide durant toute sa période de validité de 7 jours et est réutilisé à chaque appel de `/api/auth/refresh`.
2. **Absence de révocation côté serveur à la déconnexion** :
   La déconnexion supprime le cookie dans le navigateur de l'utilisateur mais n'invalide pas la signature cryptographique du jeton côté serveur. Si un cookie venait à être exfiltré avant la déconnexion, il resterait techniquement recevable par l'API jusqu'à l'échéance de ses 7 jours.
3. **Absence de détection de réutilisation** :
   En l'absence de persistance d'état en base de données, l'API ne peut détecter le rejeu simultané d'un même refresh token sur plusieurs postes.

---

## 4. Mesures de sécurité et d'atténuation

Les mesures suivantes encadrent strictement l'exposition aux risques :

1. **Atténuation du risque XSS** :
   - Le jeton d'accès n'est jamais exposé dans le stockage local persistant (`localStorage` ou `sessionStorage`).
   - L'access token a une durée de validité réduite à 15 minutes, limitant la fenêtre d'opportunité en cas d'exfiltration mémoire.
   - Absence totale d'évaluation HTML non échappée dans les composants React.
   - Politique stricte de sécurité des contenus (Content Security Policy - CSP).
   - Le refresh token est inaccessible aux scripts via l'attribut `httpOnly`.
2. **Atténuation du risque CSRF sur la route `/api/auth/refresh`** :
   - Le cookie est restreint au chemin unique `/api/auth/refresh` avec l'attribut `SameSite=Strict`.
   - Le serveur back-end contrôle obligatoirement l'en-tête d'origine (`Origin` ou `Sec-Fetch-Site`) sur cette route pour rejeter toute requête cross-site.
3. **Absence de CSRF sur les requêtes de données** :
   - Les requêtes protégées utilisent exclusivement l'en-tête `Authorization: Bearer`, insensible aux attaques CSRF standard par cookie.

---

## 5. Relation avec l'ADR-0006

L'ADR-0006 du back-end prévoyait un modèle *stateless* avec un jeton unique de 8 heures et différait les refresh tokens. L'ADR-0011 :
- Préserve le principe d'architecture *stateless* (aucune table de sessions ou de révocations en base de données).
- Réduit la durée de vie du jeton d'accès à 15 minutes (au lieu de 8 heures) pour minimiser les risques en cas de vol de jeton en mémoire.
- Introduit un refresh token de 7 jours sous cookie `httpOnly` pour maintenir la session de l'analyste sans nécessiter de base relationnelle pour le suivi de session.
- Les adaptations nécessaires côté back-end sont formalisées dans la proposition d'intégration de l'Épic E1 (`docs/proposals/PROPOSITION-auth-back-E1.md`).

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-25
