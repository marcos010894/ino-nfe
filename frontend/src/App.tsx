import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Cadastro from './pages/Cadastro';
import Layout from './components/Layout';
import Home from './pages/dashboard/Home';
import EmpresasList from './pages/empresas/EmpresasList';
import EmpresaForm from './pages/empresas/EmpresaForm';
import RegrasFiscaisList from './pages/empresas/RegrasFiscaisList';
import RegraFiscalForm from './pages/empresas/RegraFiscalForm';
import EmitirNota from './pages/empresas/EmitirNota';
import CentralDocumentos from './pages/empresas/CentralDocumentos';
import { isAuthenticated } from './lib/auth';

function PublicRoute({ children }: { children: React.ReactNode }) {
  return isAuthenticated() ? <Navigate to="/" replace /> : <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
        <Route path="/cadastro" element={<PublicRoute><Cadastro /></PublicRoute>} />
        
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="empresas" element={<EmpresasList />} />
          <Route path="empresas/nova" element={<EmpresaForm />} />
          <Route path="empresas/:id" element={<EmpresaForm />} />
          <Route path="empresas/:id/regras" element={<RegrasFiscaisList />} />
          <Route path="empresas/:id/regras/nova" element={<RegraFiscalForm />} />
          <Route path="empresas/:id/regras/:regraId" element={<RegraFiscalForm />} />
          <Route path="emitir" element={<EmitirNota />} />
          <Route path="documentos" element={<CentralDocumentos />} />
        </Route>
        
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

