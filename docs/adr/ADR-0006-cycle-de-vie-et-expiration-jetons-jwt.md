# ADR-0006 : Politique d'expiration et cycle de vie des jetons JWT

- **Date** : 2026-11-23
- **Statut** : acceptée

---

## Contexte

La décision D-12 acte l'utilisation de `PyJWT` pour l'authentification et l'autorisation des requêtes API, et la décision D-13 retient le hachage sécurisé argon2 via `pwdlib`.

Cependant, les paramètres de durée de validité des jetons d'accès, la complexité minimale des mots de passe et la gestion des sessions nécessitaient d'être standardisés pour cadrer l'implémentation de l'Épic 1.

---

## Décision

Nous retenons l'**Option A** :
1. Utilisation d'un **jeton d'accès unique (*Access Token*)** d'une durée de validité de **8 heures**, correspondant à la vacation opérationnelle standard d'un analyste DFIR en SOC/CERT.
2. Structure standard des *claims* JWT : `sub` (User ID), `email`, `iat` (Issued At) et `exp` (Expiration Time).
3. Authentification strictement *stateless* pour le MVP : aucune table de session ou liste de révocation n'est introduite en base de données, la validation s'effectuant par vérification cryptographique de la signature HMAC-SHA256 (`HS256`).
4. Politique de sécurité des mots de passe : longueur minimale de 12 caractères avec au moins 1 lettre majuscule, 1 lettre minuscule, 1 chiffre et 1 caractère spécial, contrôlée par validateur Pydantic v2.
5. Les mécanismes complexes de *refresh tokens* et de révocation dynamique sont différés en phase post-MVP.

---

## Conséquences

### Positives
- **Simplicité et robustesse** : Aucune requête en base de données requise pour authentifier les requêtes API entrantes.
- **Faible latence** : Validation cryptographique ultra-rapide par middleware FastAPI.
- **Conformité de sécurité** : Mots de passe durcis et durée de vie de jeton bornée à une journée de travail.

### Négatives / Risques
- Impossibilité d'invalider un jeton compromis avant son terme de 8h sans rotation de la clé secrète JWT globale.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & AI/Tech Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
