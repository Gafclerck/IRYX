import { http, HttpResponse } from 'msw'
import type {
  LoginRequest,
  TokenResponse,
  LogoutResponse,
  ErrorResponse,
} from '../../api/auth-types'

/**
 * Données simulées d'investigation pour le contrat cible E2 (Story F1.6).
 */
export const MOCK_CASES = [
  {
    id: 'case-001',
    organization_id: 'org-001',
    title: 'Incident Ransomware LockBit v3',
    description: 'Compromission initiale par pièce jointe malveillante',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-20T08:15:00Z',
    updated_at: '2026-11-20T09:00:00Z',
    evidence_count: 4,
  },
  {
    id: 'case-002',
    organization_id: 'org-001',
    title: 'Fuite de données confidentielles RH',
    description: 'Exfiltration massive détectée sur canal cloud non approuvé',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-19T14:30:00Z',
    updated_at: '2026-11-19T16:00:00Z',
    evidence_count: 12,
  },
  {
    id: 'case-003',
    organization_id: 'org-001',
    title: 'Attaque DDoS infrastructure Cloud',
    description: 'Saturation volumétrique des passerelles de terminaison TLS',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-18T10:00:00Z',
    updated_at: '2026-11-18T12:00:00Z',
    evidence_count: 2,
  },
  {
    id: 'case-004',
    organization_id: 'org-001',
    title: 'Compromission Active Directory Kerberoasting',
    description: 'Détection de tickets SPN chiffrés avec algorithme faible',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-17T09:20:00Z',
    updated_at: '2026-11-17T11:00:00Z',
    evidence_count: 7,
  },
  {
    id: 'case-005',
    organization_id: 'org-001',
    title: 'Exfiltration données financières via DNS',
    description: 'Canal de communication discret sur sous-domaines dynamiques',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-16T16:45:00Z',
    updated_at: '2026-11-16T18:00:00Z',
    evidence_count: 15,
  },
  {
    id: 'case-006',
    organization_id: 'org-001',
    title: 'Campagne Phishing bancaire ciblée',
    description: 'Messages usurpant la direction financière pour virement frauduleux',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-15T11:10:00Z',
    updated_at: '2026-11-15T13:30:00Z',
    evidence_count: 3,
  },
  {
    id: 'case-007',
    organization_id: 'org-001',
    title: 'Intrusion SCADA automate industriel',
    description: 'Anomalie de télécommande et modification de consignes critiques',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-14T07:30:00Z',
    updated_at: '2026-11-14T10:00:00Z',
    evidence_count: 8,
  },
  {
    id: 'case-008',
    organization_id: 'org-001',
    title: 'Usurpation identité dirigeant BEC',
    description: 'Fraude au président par ingénierie sociale avancée',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-13T13:00:00Z',
    updated_at: '2026-11-13T15:20:00Z',
    evidence_count: 1,
  },
  {
    id: 'case-009',
    organization_id: 'org-001',
    title: 'Injection SQL portail extranet',
    description: 'Extraction partielle de tables applicatives non sensibles',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-12T15:25:00Z',
    updated_at: '2026-11-12T17:00:00Z',
    evidence_count: 6,
  },
  {
    id: 'case-010',
    organization_id: 'org-001',
    title: 'Détection malware Cobalt Strike balise',
    description: 'Trafic C2 périodique vers adresse IP suspecte',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-11T18:40:00Z',
    updated_at: '2026-11-11T20:10:00Z',
    evidence_count: 9,
  },
  {
    id: 'case-011',
    organization_id: 'org-001',
    title: 'Élévation de privilèges CVE-2026-1337',
    description: 'Exploitation locale du démon d impression sur serveur linux',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-10T12:00:00Z',
    updated_at: '2026-11-10T14:00:00Z',
    evidence_count: 5,
  },
  {
    id: 'case-012',
    organization_id: 'org-001',
    title: 'Mouvement latéral SMB pass-the-hash',
    description: 'Propagation d un compte administrateur local compromis',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-09T08:50:00Z',
    updated_at: '2026-11-09T10:15:00Z',
    evidence_count: 11,
  },
  {
    id: 'case-013',
    organization_id: 'org-001',
    title: 'Compromission compte VPN sans MFA',
    description: 'Accès distant nocturne depuis géolocalisation inhabituelle',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-08T17:15:00Z',
    updated_at: '2026-11-08T19:00:00Z',
    evidence_count: 4,
  },
  {
    id: 'case-014',
    organization_id: 'org-001',
    title: 'Détournement session OAuth collaborateur',
    description: 'Jeton de rafraîchissement réutilisé hors de l entreprise',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-07T10:45:00Z',
    updated_at: '2026-11-07T12:00:00Z',
    evidence_count: 2,
  },
  {
    id: 'case-015',
    organization_id: 'org-001',
    title: 'Attaque par force brute SSH serveur bastion',
    description: 'Tentatives répétées bloquées par fail2ban et filtrage',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-06T22:30:00Z',
    updated_at: '2026-11-06T23:45:00Z',
    evidence_count: 0,
  },
  {
    id: 'case-016',
    organization_id: 'org-001',
    title: 'Analyse mémoire vivante machine compromise',
    description: 'Dump RAM station travail avec processus injecté',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-05T09:15:00Z',
    updated_at: '2026-11-05T11:30:00Z',
    evidence_count: 18,
  },
  {
    id: 'case-017',
    organization_id: 'org-001',
    title: 'Découverte porte dérobée script PowerShell',
    description: 'Persistance via tâche planifiée dissimulée',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-04T14:10:00Z',
    updated_at: '2026-11-04T16:00:00Z',
    evidence_count: 7,
  },
  {
    id: 'case-018',
    organization_id: 'org-001',
    title: 'Attaque Supply Chain paquet npm corrompu',
    description: 'Injection de code obfusqué dans dépendance tierce',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-03T16:00:00Z',
    updated_at: '2026-11-03T18:00:00Z',
    evidence_count: 13,
  },
  {
    id: 'case-019',
    organization_id: 'org-001',
    title: 'Scan de vulnérabilités agressif externe',
    description: 'Balayage de ports et énumération de services exposés',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-02T11:20:00Z',
    updated_at: '2026-11-02T12:30:00Z',
    evidence_count: 1,
  },
  {
    id: 'case-020',
    organization_id: 'org-001',
    title: 'Évasion bac à sable endpoint EDR',
    description: 'Contournement par appel direct d API système non surveillée',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-11-01T15:40:00Z',
    updated_at: '2026-11-01T17:10:00Z',
    evidence_count: 6,
  },
  {
    id: 'case-021',
    organization_id: 'org-001',
    title: 'Compromission conteneur Kubernetes',
    description: 'Échappement vers le nœud hôte via socket système',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-31T13:20:00Z',
    updated_at: '2026-10-31T15:00:00Z',
    evidence_count: 5,
  },
  {
    id: 'case-022',
    organization_id: 'org-001',
    title: 'Tentative de pivot réseau zone DMZ',
    description: 'Communication inter-VLAN bloquée par filtrage',
    status: 'review',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-30T09:10:00Z',
    updated_at: '2026-10-30T10:40:00Z',
    evidence_count: 3,
  },
  {
    id: 'case-023',
    organization_id: 'org-001',
    title: 'Vol de jetons d accès API production',
    description: 'Clés statiques trouvées dans archive publique',
    status: 'open',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-29T17:00:00Z',
    updated_at: '2026-10-29T18:30:00Z',
    evidence_count: 10,
  },
  {
    id: 'case-024',
    organization_id: 'org-001',
    title: 'Sabotage logique base de données archivage',
    description: 'Tentative de suppression d enregistrements d audit',
    status: 'closed',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-28T08:00:00Z',
    updated_at: '2026-10-28T09:15:00Z',
    evidence_count: 8,
  },
  {
    id: 'case-025',
    organization_id: 'org-001',
    title: 'Altération certificat TLS passerelle web',
    description: 'Tentative d interposition sur flux chiffré',
    status: 'in_progress',
    created_by: 'analyste@iryx.local',
    created_at: '2026-10-27T14:50:00Z',
    updated_at: '2026-10-27T16:20:00Z',
    evidence_count: 2,
  },
]

const INITIAL_MOCK_CASES = [...MOCK_CASES]

/**
 * Réinitialise la liste des dossiers simulés à son état initial (Story F1.7).
 */
export function resetMockCases() {
  MOCK_CASES.length = 0
  MOCK_CASES.push(...INITIAL_MOCK_CASES)
}

/**
 * Handlers MSW simulant les routes réseau de l'application IRYX.
 *
 * Routes d'authentification simulées d'après le contrat cible (Stories F1.2 et F1.4) :
 * - POST /api/v1/auth/login (simulée, contrat cible : auth-contrat-cible.yaml)
 * - POST /api/v1/auth/refresh (simulée, contrat cible : auth-contrat-cible.yaml)
 * - POST /api/v1/auth/logout (simulée, contrat cible : auth-contrat-cible.yaml)
 *
 * Routes protégées simulées d'après le contrat OpenAPI (Stories F1.3, F1.6 et F1.7) :
 * - GET /api/v1/auth/me (simulée, contrat cible : openapi.json)
 * - GET /api/v1/cases (simulée, contrat cible : openapi.json)
 * - POST /api/v1/cases (simulée, contrat cible : openapi.json)
 */
export const handlers = [
  http.get('*/api/test-simulation', () => {
    return HttpResponse.json({ status: 'ok', simulation: true })
  }),

  http.get('*/api/health', () => {
    return HttpResponse.json({ status: 'healthy' })
  }),

  // POST /api/v1/auth/login (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/login', async ({ request }) => {
    try {
      const body = (await request.json()) as Partial<LoginRequest>
      const { email, password } = body

      if (!email || !password) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Champs obligatoires manquants.' },
          { status: 400 },
        )
      }

      // Simulation compte inactif / révoqué (403)
      if (email === 'bloque@iryx.local') {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Compte inactif ou accès révoqué. Contactez votre administrateur.' },
          { status: 403 },
        )
      }

      // Simulation erreur serveur 500
      if (email === 'serveur-erreur@iryx.local') {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Erreur interne du serveur.' },
          { status: 500 },
        )
      }

      // Simulation identifiants incorrects (401)
      if (
        password === 'mauvaismdp' ||
        password === 'wrong-password' ||
        email === 'inconnu@iryx.local'
      ) {
        return HttpResponse.json<ErrorResponse>(
          { detail: 'Identifiants incorrects.' },
          { status: 401 },
        )
      }

      // Cas nominal (200) : délivrance de l'access token (15 min) et positionnement du cookie refresh (7 j)
      const tokenResponse: TokenResponse = {
        access_token: 'mock-access-token-bearer-15min',
        token_type: 'bearer',
        expires_in: 900,
      }

      return HttpResponse.json(tokenResponse, {
        status: 200,
        headers: {
          'Set-Cookie':
            'refresh_token=mock-refresh-token-jwt-7d; Path=/api/v1/auth/refresh; Max-Age=604800; HttpOnly; Secure; SameSite=Strict',
        },
      })
    } catch {
      return HttpResponse.json<ErrorResponse>({ detail: 'Requête malformée.' }, { status: 400 })
    }
  }),

  // POST /api/v1/auth/refresh (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/refresh', async ({ request }) => {
    const origin = request.headers.get('Origin')
    // Simulation rejet anti-CSRF
    if (origin === 'http://malicious-site.local') {
      return HttpResponse.json<ErrorResponse>({ detail: 'Origine non autorisée.' }, { status: 403 })
    }

    const simHeader = request.headers.get('X-Simulation-Refresh')
    if (simHeader === 'network-error') {
      return HttpResponse.error()
    }

    const cookieHeader = request.headers.get('Cookie')
    if (
      simHeader === 'expired' ||
      cookieHeader?.includes('expired') ||
      cookieHeader?.includes('invalid')
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Session expirée. Veuillez vous reconnecter.' },
        { status: 401 },
      )
    }

    const tokenResponse: TokenResponse = {
      access_token: 'mock-refreshed-access-token-bearer-15min',
      token_type: 'bearer',
      expires_in: 900,
    }

    return HttpResponse.json(tokenResponse, { status: 200 })
  }),

  // POST /api/v1/auth/logout (simulée, contrat cible : auth-contrat-cible.yaml)
  http.post('*/api/v1/auth/logout', async () => {
    const logoutResponse: LogoutResponse = {
      message: 'Déconnexion réussie.',
    }

    return HttpResponse.json(logoutResponse, {
      status: 200,
      headers: {
        'Set-Cookie':
          'refresh_token=; Path=/api/v1/auth/refresh; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Expires=Thu, 01 Jan 1970 00:00:00 GMT',
      },
    })
  }),

  // GET /api/v1/auth/me (simulée, contrat cible : openapi.json - Story F1.3)
  http.get('*/api/v1/auth/me', ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    if (token === 'mock-server-error-token' || token.includes('server-error')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur.' },
        { status: 500 },
      )
    }

    return HttpResponse.json(
      {
        id: '00000000-0000-0000-0000-000000000001',
        email: 'analyste@iryx.local',
        is_active: true,
        created_at: '2026-11-25T00:00:00Z',
        updated_at: '2026-11-25T00:00:00Z',
      },
      { status: 200 },
    )
  }),

  // GET /api/v1/cases (simulée, contrat cible : openapi.json - Stories F1.3 et F1.6)
  http.get('*/api/v1/cases', ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const simHeader = request.headers.get('X-Simulation-Cases')

    // Simulation accès refusé 403 Forbidden (Story F1.6)
    if (token === 'mock-forbidden-token' || simHeader === 'forbidden') {
      return HttpResponse.json<ErrorResponse>(
        {
          detail:
            "Accès refusé. Vous n'avez pas accès aux dossiers de cette organisation. Veuillez contacter votre administrateur.",
        },
        { status: 403 },
      )
    }

    // Simulation erreur interne 500 (Story F1.6)
    if (
      token === 'mock-server-error-token' ||
      token.includes('server-error') ||
      simHeader === 'server-error'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors de la récupération des dossiers.' },
        { status: 500 },
      )
    }

    // Simulation organisation sans dossier ou recherche infructueuse (Story F1.6)
    if (simHeader === 'empty') {
      return HttpResponse.json(
        {
          items: [],
          total: 0,
          total_items: 0,
          limit: 10,
          offset: 0,
          has_more: false,
        },
        { status: 200 },
      )
    }

    const url = new URL(request.url)
    const hasLimit = url.searchParams.has('limit')
    const hasOffset = url.searchParams.has('offset')
    const hasSearch = url.searchParams.has('search')

    // Règle de compatibilité ascendante stricte avec les tests F1.3 et F1.4
    // (qui appellent GET /api/v1/cases sans paramètre de pagination et attendent items: [])
    if (!hasLimit && !hasOffset && !hasSearch) {
      return HttpResponse.json(
        {
          items: [],
          total: 0,
          total_items: 0,
          limit: 20,
          offset: 0,
          has_more: false,
        },
        { status: 200 },
      )
    }

    const limitParam = parseInt(url.searchParams.get('limit') || '10', 10)
    const limit = isNaN(limitParam) || limitParam <= 0 ? 10 : Math.min(limitParam, 100)
    const offsetParam = parseInt(url.searchParams.get('offset') || '0', 10)
    const offset = isNaN(offsetParam) || offsetParam < 0 ? 0 : offsetParam
    const search = url.searchParams.get('search')?.trim().toLowerCase() || ''

    let filtered = MOCK_CASES
    if (search) {
      filtered = MOCK_CASES.filter(
        (c) =>
          c.title.toLowerCase().includes(search) ||
          (c.description && c.description.toLowerCase().includes(search)),
      )
    }

    const total = filtered.length
    const items = filtered.slice(offset, offset + limit)
    const hasMore = offset + items.length < total

    return HttpResponse.json(
      {
        items,
        total,
        total_items: total,
        limit,
        offset,
        has_more: hasMore,
      },
      { status: 200 },
    )
  }),

  /**
   * Création d'un nouveau dossier d'investigation en modale (Story F1.7).
   * Route cible : POST /api/v1/cases
   * Contrat cible : openapi.json (simulée E2)
   */
  http.post('*/api/v1/cases', async ({ request }) => {
    const authHeader = request.headers.get('Authorization')

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const token = authHeader.replace('Bearer ', '').trim()

    if (token === 'mock-expired-token' || token.includes('expired')) {
      return HttpResponse.json<ErrorResponse>(
        { detail: "Jeton d'accès expiré ou absent." },
        { status: 401 },
      )
    }

    const simHeader =
      request.headers.get('X-Simulation-Create-Case') || request.headers.get('X-Simulation-Cases')

    // Simulation accès refusé 403 Forbidden (Story F1.7)
    if (token === 'mock-forbidden-token' || simHeader === 'forbidden') {
      return HttpResponse.json<ErrorResponse>(
        {
          detail:
            "Vous n'avez pas les autorisations nécessaires pour créer un dossier dans cette organisation.",
        },
        { status: 403 },
      )
    }

    // Simulation erreur interne 500 (Story F1.7)
    if (
      token === 'mock-server-error-token' ||
      token.includes('server-error') ||
      simHeader === 'server-error' ||
      simHeader === '500'
    ) {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Erreur interne du serveur lors de la création du dossier.' },
        { status: 500 },
      )
    }

    // Simulation rejet de validation serveur 400 (Story F1.7)
    if (simHeader === 'validation-error' || simHeader === '400') {
      return HttpResponse.json(
        {
          detail: 'Données de dossier invalides.',
          errors: {
            title: 'Ce titre de dossier est déjà utilisé dans votre organisation.',
          },
        },
        { status: 400 },
      )
    }

    let body: Record<string, unknown> = {}
    try {
      body = (await request.json()) as Record<string, unknown>
    } catch {
      return HttpResponse.json<ErrorResponse>(
        { detail: 'Format de corps de requête invalide.' },
        { status: 400 },
      )
    }

    const title = typeof body.title === 'string' ? body.title.trim() : ''
    const description = typeof body.description === 'string' ? body.description.trim() : null
    const incidentDate = typeof body.incident_date === 'string' ? body.incident_date.trim() : ''
    const incidentType = typeof body.incident_type === 'string' ? body.incident_type.trim() : ''
    const affectedSystems =
      typeof body.affected_systems === 'string' ? body.affected_systems.trim() : ''

    // Validation minimale côté serveur (Story F1.7)
    if (!title) {
      return HttpResponse.json(
        {
          detail: 'Le titre du dossier est obligatoire.',
          errors: { title: 'Le titre du dossier est obligatoire.' },
        },
        { status: 422 },
      )
    }

    const newCase = {
      id: `case-${Date.now()}`,
      organization_id: 'org-001',
      title,
      description: description || '',
      status: 'open' as const,
      created_by: 'analyste@iryx.local',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      evidence_count: 0,
      incident_date: incidentDate || new Date().toISOString(),
      incident_type: incidentType || 'a_decider',
      affected_systems: affectedSystems,
    }

    MOCK_CASES.unshift(newCase)

    return HttpResponse.json(newCase, { status: 201 })
  }),
]
