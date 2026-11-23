# ADR-0005 : Stratégie de téléversement et streaming pour preuves volumineuses

- **Date** : 2026-11-23
- **Statut** : acceptée

---

## Contexte

Le champ `file_size` de l'entité `Evidence` (`docs/03-modele-de-donnees.md`) est un entier 64 bits (`BigInteger`), permettant d'ingérer des fichiers forensiques lourds (images disques, captures de mémoire vive RAM de 8 Go à 32 Go, archives de journaux d'événements).

FastAPI / Starlette charge par défaut les requêtes `multipart/form-data` en mémoire vive jusqu'à un seuil avant de créer des fichiers temporaires (SpoolFile). Un téléversement non bridé de plusieurs dizaines de gigaoctets risque d'épuiser la mémoire vive (OOM) ou l'espace temporaire du conteneur API.

---

## Décision

Nous retenons l'**Option A** :
1. Implémentation d'un streaming asynchrone par morceaux (*chunked streaming*) via `UploadFile.read(chunk_size)` avec un tampon mémoire fixe de 64 Ko.
2. Écriture directe des flux de données sur le volume de stockage persistant scellé (`/data/evidence/`).
3. Calcul simultané de l'empreinte cryptographique SHA-256 au fil de l'eau via le module standard `hashlib` durant l'écriture disque, sans relecture ultérieure.
4. Plafonnement de la taille maximale par un paramètre de configuration strict `MAX_EVIDENCE_SIZE_GB` (valeur par défaut : 16 Go). Tout dépassement interrompt immédiatement le téléversement avec un code HTTP 413 (Payload Too Large) et purge le fichier temporaire partiel.

---

## Conséquences

### Positives
- **Empreinte mémoire constante** : Consommation de RAM bornée à 64 Ko par transfert actif, quel que soit le volume de la preuve.
- **Efficacité I/O optimale** : Scellement SHA-256 réalisé en une seule passe d'écriture disque.
- **Résilience** : Protection de l'API contre les dénis de service par saturation mémoire ou disque.

### Négatives / Risques
- Nécessite la détection des coupures réseau inopinées côté client pour nettoyer les fragments incomplets.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & AI/Tech Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
