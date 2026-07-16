import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import "@/App.css";
import { useAuth } from "@/contexts/AuthContext";
import Login from "@/pages/Login";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import AcceptInvitation from "@/pages/AcceptInvitation";
import ChangePassword from "@/pages/ChangePassword";
import Dashboard from "@/pages/Dashboard";
import UsersPage from "@/pages/UsersPage";
import RolesPage from "@/pages/RolesPage";
import CompanyPage from "@/pages/CompanyPage";
import SequencesPage from "@/pages/SequencesPage";
import AttachmentsPage from "@/pages/AttachmentsPage";
import AuditPage from "@/pages/AuditPage";
import NotificationsPage from "@/pages/NotificationsPage";
import SessionsPage from "@/pages/SessionsPage";
import EmailLogsPage from "@/pages/EmailLogsPage";
import SearchPage from "@/pages/SearchPage";
import LeadsPage from "@/pages/LeadsPage";
import LeadDetailPage from "@/pages/LeadDetailPage";
import CustomersPage from "@/pages/CustomersPage";
import CustomerDetailPage from "@/pages/CustomerDetailPage";
import ContactsPage from "@/pages/ContactsPage";
import TasksPage from "@/pages/TasksPage";
import CalendarPage from "@/pages/CalendarPage";
import GoalsPage from "@/pages/GoalsPage";
import WhatsAppLogsPage from "@/pages/WhatsAppLogsPage";
import QuotesPage from "@/pages/QuotesPage";
import QuoteEditorPage from "@/pages/QuoteEditorPage";
import PricelistsPage from "@/pages/PricelistsPage";
import TemplatesPage from "@/pages/TemplatesPage";
import ClausesPage from "@/pages/ClausesPage";
import PublicQuotePage from "@/pages/PublicQuotePage";
import OnboardingWizard from "@/pages/OnboardingWizard";
import {
  SurveysPage, SalesOrdersPage, SuppliersPage, PurchaseOrdersPage,
  ItemsPage, ProductionOrdersPage, QCPage, ServiceTicketsPage,
  InstallationPlansPage, PaymentPlansPage, AICFOPage,
} from "@/pages/ErpModulePages";
import ParametricConfiguratorPage from "@/pages/ParametricConfiguratorPage";
import ParametricAdminPage from "@/pages/ParametricAdminPage";
import TechnicalSchedulesPage from "@/pages/TechnicalSchedulesPage";
import PublicSchedulePage from "@/pages/PublicSchedulePage";
import LegalEntitiesPage from "@/pages/LegalEntitiesPage";
import TreasuryCFOPage from "@/pages/TreasuryCFOPage";
import SaaSPlatformPage from "@/pages/SaaSPlatformPage";
import ProductCatalogPage from "@/pages/ProductCatalogPage";
import SiteConditionsForm from "@/pages/SiteConditionsForm";
import LandingPage from "@/pages/LandingPage";
import PlatformSiteConfigPage from "@/pages/PlatformSiteConfigPage";
import QuoteStructurePage from "@/pages/QuoteStructurePage";
import PricingHubPage from "@/pages/PricingHubPage";
import GeometryBuilderPage from "@/pages/GeometryBuilderPage";
import PricelistImporterPage from "@/pages/PricelistImporterPage";
import ContractsPage from "@/pages/ContractsPage";
import ContractViewerPage from "@/pages/ContractViewerPage";
import AppLayout from "@/layouts/AppLayout";

function Protected({ children }) {
  const { user } = useAuth();
  if (user === undefined) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="overline" data-testid="app-loading">Caricamento…</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return children;
}

function App() {
  return (
    <div className="App">
      <Routes>
        <Route path="/landing" element={<LandingPage />} />
        <Route path="/login" element={<Login />} />
        <Route path="/p/:token" element={<PublicQuotePage />} />
        <Route path="/p/schedule/:token" element={<PublicSchedulePage />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/accept-invitation" element={<AcceptInvitation />} />
        <Route path="/change-password" element={<ChangePassword />} />
        <Route path="/onboarding" element={<Protected><OnboardingWizard /></Protected>} />
        <Route
          path="/"
          element={
            <Protected>
              <AppLayout />
            </Protected>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="leads" element={<LeadsPage />} />
          <Route path="leads/:id" element={<LeadDetailPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="customers/:id" element={<CustomerDetailPage />} />
          <Route path="contacts" element={<ContactsPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="goals" element={<GoalsPage />} />
          <Route path="whatsapp-logs" element={<WhatsAppLogsPage />} />
          <Route path="quotes" element={<QuotesPage />} />
          <Route path="quotes/:id" element={<QuoteEditorPage />} />
          <Route path="pricelists" element={<PricelistsPage />} />
          <Route path="templates" element={<TemplatesPage />} />
          <Route path="clauses" element={<ClausesPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="company" element={<CompanyPage />} />
          <Route path="sequences" element={<SequencesPage />} />
          <Route path="attachments" element={<AttachmentsPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="email-logs" element={<EmailLogsPage />} />
          <Route path="search" element={<SearchPage />} />
          {/* M4..M17 — Operational ERP modules */}
          <Route path="surveys" element={<SurveysPage />} />
          <Route path="sales-orders" element={<SalesOrdersPage />} />
          <Route path="suppliers" element={<SuppliersPage />} />
          <Route path="purchase-orders" element={<PurchaseOrdersPage />} />
          <Route path="items" element={<ItemsPage />} />
          <Route path="production-orders" element={<ProductionOrdersPage />} />
          <Route path="qc" element={<QCPage />} />
          <Route path="service-tickets" element={<ServiceTicketsPage />} />
          <Route path="installation-plans" element={<InstallationPlansPage />} />
          <Route path="payment-plans" element={<PaymentPlansPage />} />
          <Route path="ai-cfo" element={<AICFOPage />} />
          <Route path="parametric" element={<ParametricConfiguratorPage />} />
          <Route path="parametric/admin" element={<ParametricAdminPage />} />
          <Route path="technical-schedules" element={<TechnicalSchedulesPage />} />
          <Route path="legal-entities" element={<LegalEntitiesPage />} />
          <Route path="cfo" element={<TreasuryCFOPage />} />
          <Route path="saas-platform" element={<SaaSPlatformPage />} />
          <Route path="product-catalog" element={<ProductCatalogPage />} />
          <Route path="site-conditions" element={<SiteConditionsForm />} />
          <Route path="platform-site-config" element={<PlatformSiteConfigPage />} />
          <Route path="quote-structure" element={<QuoteStructurePage />} />
          <Route path="quote-structure/:quoteId" element={<QuoteStructurePage />} />
          <Route path="pricing-hub" element={<PricingHubPage />} />
          <Route path="geometry-builder" element={<GeometryBuilderPage />} />
          <Route path="pricelist-importer" element={<PricelistImporterPage />} />
          <Route path="contracts" element={<ContractsPage />} />
          <Route path="contracts/:id" element={<ContractViewerPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default App;
