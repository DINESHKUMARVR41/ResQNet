import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

async function loadApi(baseUrl = 'http://127.0.0.1:8000/api/v1') {
  vi.stubEnv('VITE_API_URL', baseUrl)
  return import('../src/lib/api')
}

describe('ResQNet API client', () => {
  beforeEach(() => vi.resetModules())

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('uses the configured base URL and sends login JSON with the expected fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      access_token: 'test-token',
      token_type: 'bearer',
      user: { id: '1', full_name: 'Demo Citizen', email: 'citizen@resqnet.demo', role: 'citizen' },
    }), { headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    const { api } = await loadApi('http://127.0.0.1:8000/api/v1/')

    await api.login('citizen@resqnet.demo', 'password')

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://127.0.0.1:8000/api/v1/auth/login')
    expect(options.method).toBe('POST')
    expect(new Headers(options.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(options.body)).toEqual({ email: 'citizen@resqnet.demo', password: 'password' })
  })

  it('reports an unreachable configured API URL instead of a generic fetch error', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchMock)
    const { api } = await loadApi('http://127.0.0.1:8003/api/v1')

    await expect(api.login('citizen@resqnet.demo', 'password')).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
      message: 'Unable to connect to ResQNet server. Please check whether the backend is running.',
    })
    expect(fetchMock.mock.calls[0][0]).toBe('http://127.0.0.1:8003/api/v1/auth/login')
  })

  it.each([
    [401, 'Invalid email or password.'],
    [403, 'You are not authorized to access this dashboard.'],
    [500, 'ResQNet server encountered an error. Please try again.'],
  ])('maps HTTP %s to a useful message without exposing server details', async (status, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'internal detail must not be shown' }),
      { status, headers: { 'Content-Type': 'application/json' } },
    )))
    const { api } = await loadApi()

    await expect(api.login('citizen@resqnet.demo', 'password')).rejects.toMatchObject({ status, message })
  })

  it('handles non-JSON server errors without exposing response content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      'internal stack trace',
      { status: 500, headers: { 'Content-Type': 'text/plain' } },
    )))
    const { api } = await loadApi()

    await expect(api.login('citizen@resqnet.demo', 'password')).rejects.toMatchObject({
      status: 500,
      message: 'ResQNet server encountered an error. Please try again.',
    })
  })

  it('handles empty success responses and does not set multipart Content-Type manually', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const { api } = await loadApi()

    await expect(api.uploadAudioReport('test-token', 'RQ-DEMO-1', new FormData())).resolves.toBeUndefined()
    const options = fetchMock.mock.calls[0][1]
    expect(new Headers(options.headers).has('Content-Type')).toBe(false)
  })
})
