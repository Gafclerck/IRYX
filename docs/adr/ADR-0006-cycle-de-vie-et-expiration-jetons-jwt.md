# ADR-0006 : Politique d'expiration et cycle de vie des jetons JWT

- **Date** : 2026-11-23
- **Mise à jour** : 2026-11-25 (alignement Story 1.4 : 60 min et contrôle de l'utilisateur actif en base)
- **Statut** : acceptée

---

## Contexte

La décision D-12 acte l'utilisation de `PyJWT` pour l'authentification et l'autorisation des requêtes API, et la décision D-13 retient le hachage sécurisé argon2 via `pwdlib`.

Cependant, les paramètres de durée de validité des jetons d'accès, la complexité minimale des mots de passe et la gestion des sessions nécessitaient d'être standardisés pour cadrer l'implémentation de l'Épic 1.

---

## Décision

Nous retenons l'**Option A** :
1. Utilisation d'un **jeton d'accès unique (*Access Token*)** d'une durée de validité de **60 minutes (3600 secondes)**, configurable via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`.
2. Structure standard des *claims* JWT : `sub` (User ID), `email`, `iat` (Issued At) et `exp` (Expiration Time).
3. Pas de table de session ni de liste de révocation pour le MVP : la validation combine la vérification cryptographique HMAC-SHA256 (`HS256`) et une requête de contrôle dans `get_current_user` qui vérifie l'existence et l'état actif de l'utilisateur.
4. Politique de sécurité des mots de passe : longueur minimale de 12 caractères avec au moins 1 lettre majuscule, 1 lettre minuscule, 1 chiffre et 1 caractère spécial, contrôlée par validateur Pydantic v2.
5. Les mécanismes complexes de *refresh tokens* et de révocation dynamique sont différés en phase post-MVP.

---

## Conséquences

### Positives
- **Simplicité et robustesse** : Aucune table de session ; une seule requête légère valide l'utilisateur actif à chaque requête authentifiée.
- **Faible latence** : Validation cryptographique rapide par middleware FastAPI, sans jointure sur une table de sessions.
- **Conformité de sécurité** : Mots de passe durcis et durée de vie de jeton bornée à 60 minutes.

### Négatives / Risques
- Impossibilité d'invalider un jeton compromis avant son terme de 60 min sans rotation de la clé secrète JWT globale.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & AI/Tech Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
