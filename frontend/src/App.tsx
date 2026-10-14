import { useEffect, useState } from 'react'

type OllamaStatus = {
  status?: string
  url?: string
  models?: string[]
  configured_model?: string | null
  model_installed?: boolean
}

type ApiStatus = {
  api?: string
  db?: string
  ollama?: OllamaStatus
}

export default function App() {
  const [status, setStatus] = useState<ApiStatus | string>('checking...')
  const [reply, setReply] = useState('')

  useEffect(() => {
    fetch('/api/v1/status')
      .then((response) => response.json())
      .then(setStatus)
      .catch(() => setStatus('API unreachable'))
  }, [])

  async function testModel() {
    setReply('Waiting for the model...')
    try {
      const response = await fetch('/api/v1/ollama/test')
      const data = await response.json()
      if (response.ok) {
        setReply(`${data.model}: ${data.response}`)
      } else {
        setReply(data.detail ?? 'Request failed')
      }
    } catch {
      setReply('API unreachable')
    }
  }

  const ollama = typeof status === 'object' ? status.ollama : undefined

  return (
    <main>
      <h1>Operon</h1>
      {typeof status === 'string' ? (
        <p>{status}</p>
      ) : (
        <section>
          <p>
            <strong>Configured model:</strong>{' '}
            {ollama?.configured_model ?? 'not set (add OLLAMA_MODEL to .env)'}
          </p>
          <p>
            <strong>Ollama URL:</strong> {ollama?.url ?? 'unknown'}
          </p>
          <p>
            <strong>Reachable from API:</strong> {ollama?.status ?? 'unknown'}
          </p>
          <p>
            <strong>Installed on host:</strong>{' '}
            {ollama?.models?.length ? ollama.models.join(', ') : 'none reported'}
          </p>
        </section>
      )}
      <button onClick={testModel}>Test the model via the API</button>
      <p>{reply}</p>
      <pre>{JSON.stringify(status, null, 2)}</pre>
    </main>
  )
}
