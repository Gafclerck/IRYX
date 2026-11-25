import { describe, it, expect } from 'vitest'

describe('Couche de simulation MSW', () => {
  it('démarre et intercepte les requêtes de test en mode simulation', async () => {
    const response = await fetch('http://localhost/api/test-simulation')
    expect(response.status).toBe(200)

    const data = (await response.json()) as { status: string; simulation: boolean }
    expect(data).toEqual({ status: 'ok', simulation: true })
  })

  it('intercepte le point de terminaison /api/health', async () => {
    const response = await fetch('http://localhost/api/health')
    expect(response.status).toBe(200)

    const data = (await response.json()) as { status: string }
    expect(data).toEqual({ status: 'healthy' })
  })
})
