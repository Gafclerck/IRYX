# Proposition Technique : Adaptation de l'Authentification Back-End (Épic E1)

- **Date** : 2026-11-25
- **Statut** : À intégrer par l'AI/Tech Lead dans la story E1 en cours
- **Auteurs** : Team Lead & Product Lead (Front-End IRYX)
- **Références** : Décisions D1, D3, D6 et document d'architecture ADR-0011

---

## 1. Objet et Motivation de la Proposition

Dans le cadre de l'intégration de l'interface utilisateur et de la sécurisation des sessions d'enquêteurs, les décisions d'architecture D1, D3 et D6 ont été formellement validées pour le cycle front-end. 

Cette proposition synthétise les adaptations techniques requises sur la story E1 du back-end (spécification `spec-1-4-service-authentification-jwt-endpoint-connexion-api.md`) afin de garantir l'interopérabilité sans délai lors de la publication du contrat OpenAPI.

---

## 2. Synthèse des Décisions Validées à Appliquer

| Identifiant | Domaine | Règle arrêtée |
|---|---|---|
| D1 | Transport du Refresh Token | Cookie HTTP avec attributs `httpOnly`, `Secure`, `SameSite=Strict`, restreint au chemin `/api/auth/refresh`. |
| D3 | Cycle de vie des jetons | Jeton d'accès de 15 minutes ; Jeton de renouvellement de 7 jours. |
| D6 | Architecture du Refresh Token | Modèle *stateless simple* : signé cryptographiquement, sans table en base de données, sans rotation unitaire, sans détection de réutilisation. Déconnexion par suppression du cookie côté navigateur sans révocation côté serveur. |

---

## 3. Spécification des Modifications Requises sur l'Épic E1

### 3.1 Durée de validité de l'Access Token (D3)
- L'ADR-0006 initiale prévoyait une validité de 8 heures pour le jeton unique.
- **Modification** : La durée de validité du jeton d'accès Bearer est abaissée à **15 minutes**.
- Le jeton est renvoyé dans le corps de réponse JSON des routes de connexion et de renouvellement sous la clé standard `access_token` avec `token_type: "bearer"`.

### 3.2 Format et signature du Refresh Token (D3, D6)
- **Format** : Jeton signé cryptographiquement selon l'algorithme HMAC-SHA256 (`HS256`) ou signature asymétrique, utilisant le secret serveur existant.
- **Contenu des revendications (claims)** : Identifiant utilisateur (`sub`), typologie de jeton (`type: "refresh"`), horodatage d'émission (`iat`) et date d'expiration fixée à 7 jours (`exp`).
- **Absence de persistance** : Conformément à D6, aucune table relationnelle ni modèle SQLAlchemy supplémentaire n'est requis en base de données.

### 3.3 Paramétrage du Cookie de Renouvellement (D1)
Le serveur back-end doit injecter le refresh token via l'en-tête de réponse `Set-Cookie` lors de la connexion, avec les directives obligatoires suivantes :
- Attribut `HttpOnly` : Interdit formellement l'accès au jeton par le JavaScript du navigateur.
- Attribut `Secure` : Imposé pour tout échange chiffré HTTPS.
- Attribut `SameSite=Strict` : Bloque l'envoi du cookie lors de navigations transverses.
- Attribut `Path=/api/auth/refresh` : Restreint l'exposition du cookie au seul endpoint de renouvellement.
- Durée de vie (`Max-Age`) : 604800 secondes (7 jours).

### 3.4 Spécification des Endpoints d'Authentification

#### 1. Route de connexion (`POST /api/auth/login`)
- **Entrée** : Identifiants utilisateur (adresse électronique et mot de passe).
- **Traitement** : Vérification de mot de passe par hachage argon2 via pwdlib.
- **Sortie** : 
  - Corps HTTP 200 contenant l'access token de 15 minutes.
  - En-tête `Set-Cookie` positionnant le refresh token de 7 jours selon les attributs ci-dessus.

#### 2. Route de renouvellement (`POST /api/auth/refresh`)
- **Contrôle préalable anti-CSRF** : Vérification stricte de l'en-tête d'origine (`Origin` ou `Sec-Fetch-Site`) comparée au nom de domaine attendu de l'application. Rejet par code HTTP 403 en cas de discordance.
- **Traitement** : Extraction du refresh token depuis le cookie ; validation de signature et d'expiration.
- **Sortie** :
  - Corps HTTP 200 contenant un nouvel access token de 15 minutes.
  - Conformément à D6, le même refresh token est conservé (pas de nouveau cookie émis).

#### 3. Route de déconnexion (`POST /api/auth/logout`)
- **Traitement** : Émission d'un en-tête `Set-Cookie` invalidant le cookie côté client (valeur vidée avec `Max-Age=0` ou expiration dans le passé).
- **Sortie** : Réponse HTTP 200 confirmant la déconnexion.
- **Note modèle D6** : Aucune écriture ni marquage de révocation en base de données.

---

## 4. Risques Acceptés et Consignés (D6)

L'AI/Tech Lead doit acter que ce modèle sans état comporte les risques suivants, acceptés par l'équipe produit pour le MVP :
1. **Validité continue du jeton** : Le refresh token ne peut être invalidé unitairement avant son expiration de 7 jours.
2. **Déconnexion locale uniquement** : La déconnexion supprime l'accès dans le navigateur actif mais ne révoque pas le jeton au niveau du serveur.

---

Document transmis pour intégration technique par l'AI/Tech Lead du back-end dans la story E1 en cours.
