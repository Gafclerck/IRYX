# ADR-0009 : Procédure de mise à jour hors-ligne des symboles Volatility 3

- **Date** : 2026-11-23
- **Statut** : acceptée

---

## Contexte

La décision D-26 impose une exécution de Volatility 3 en environnement strictement hors ligne (`network_mode: none`) avec une archive officielle de symboles Windows ISF préchargée (`windows.zip` vérifié par empreinte SHA-256).

Si un dump de mémoire vive issu d'une version récente de Windows non couverte par l'archive initiale est soumis à l'investigation, Volatility échoue par manque de symboles sans pouvoir contacter les serveurs de symboles Microsoft sur Internet.

---

## Décision

Nous retenons l'**Option A** :
1. Mise en place d'un sous-répertoire `/opt/volatility3/custom_symbols` monté en volume lecture seule (`ro`) dans le conteneur d'outils forensiques.
2. Procédure administrative hors ligne : tout ajout de symboles requiert le téléchargement préalable hors site d'une table ISF officielle, la vérification de son empreinte SHA-256, et son dépôt manuel par l'administrateur système dans le répertoire dédié.
3. Volatility 3 est configuré pour scruter conjointement l'archive native et le répertoire de symboles complémentaires monté en lecture seule.
4. L'isolation réseau (`network_mode: none`) reste inviolable en toutes circonstances ; aucune connexion réseau sortante n'est autorisée pour Volatility.

---

## Conséquences

### Positives
- **Sanctuarisation de la sécurité forensique** : Maintien strict du confinement air-gap (zéro fuite de données d'enquête).
- **Flexibilité opérationnelle** : Possibilité d'étendre la couverture des versions Windows sans reconstruction ni interruption du conteneur.
- **Traçabilité** : Chaque pack de symboles additionnel est audité et documenté par son hash SHA-256.

### Négatives / Risques
- Nécessite une manipulation manuelle par l'administrateur en cas de découverte d'un dump issu d'un build Windows inconnu.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & AI/Tech Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
