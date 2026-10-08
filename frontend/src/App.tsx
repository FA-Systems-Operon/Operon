"""Frontend home page component."""


function App() {
  return (
    <div style={{ textAlign: 'center', padding: '2rem' }}>
      <h1>Operon</h1>
      <p>AI-powered business operations platform</p>
      <p>
        Backend API: <a href="http://localhost:8080/docs">http://localhost:8080/docs</a>
      </p>
    </div>
  )
}

export default App
