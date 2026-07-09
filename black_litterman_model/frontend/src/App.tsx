// <Routes> definition + <Navbar> on every page (§3)
import { Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import ManualViews from './pages/ManualViews'
import MLViews from './pages/MLViews'
import Results from './pages/Results'
import Setup from './pages/Setup'

export default function App() {
  return (
    <>
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/setup" replace />} />
          <Route path="/setup" element={<Setup />} />
          <Route path="/views" element={<ManualViews />} />
          <Route path="/ml-views" element={<MLViews />} />
          <Route path="/results" element={<Results />} />
        </Routes>
      </main>
    </>
  )
}
