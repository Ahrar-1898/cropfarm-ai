import { Link, NavLink } from 'react-router-dom'
import { ChevronDown, Leaf, LogOut, PanelLeftClose, PanelLeftOpen, Settings } from 'lucide-react'
import { appNavigation } from '../navigation'

type SidebarProps = {
  collapsed: boolean
  mobileOpen: boolean
  onToggleCollapsed: () => void
  onCloseMobile: () => void
  onSignOut: () => void
}

export function Sidebar({
  collapsed,
  mobileOpen,
  onToggleCollapsed,
  onCloseMobile,
  onSignOut,
}: SidebarProps) {
  return (
    <>
      {mobileOpen && (
        <button
          aria-label="Close navigation"
          className="sidebar-scrim"
          onClick={onCloseMobile}
          type="button"
        />
      )}
      <aside
        aria-label="Main sidebar"
        className={`sidebar${collapsed ? ' sidebar-collapsed' : ''}${mobileOpen ? ' sidebar-mobile-open' : ''}`}
      >
        <div className="sidebar-brand-row">
          <Link aria-label="CropFarmAI overview" className="brand-lockup" onClick={onCloseMobile} to="/">
            <span className="brand-leaf">
              <Leaf aria-hidden="true" size={25} strokeWidth={2.2} />
            </span>
            <span className="brand-words">
              <strong>CropFarm<span>AI</span></strong>
              <small>Smart Farming. Better Tomorrow.</small>
            </span>
          </Link>
          <button
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="sidebar-collapse"
            onClick={onToggleCollapsed}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            type="button"
          >
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
        </div>

        <div className="sidebar-navigation">
          <p className="nav-section-label">MAIN MENU</p>
          <nav aria-label="Dashboard pages" className="nav-list">
            {appNavigation.slice(0, 8).map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  aria-label={item.label}
                  className={({ isActive }) => `nav-link${isActive ? ' nav-link-active' : ''}`}
                  end={item.to === '/'}
                  key={item.to}
                  onClick={onCloseMobile}
                  title={collapsed ? item.label : undefined}
                  to={item.to}
                >
                  <Icon aria-hidden="true" size={19} strokeWidth={1.9} />
                  <span>{item.label}</span>
                </NavLink>
              )
            })}
          </nav>
          <p className="nav-section-label nav-section-account">ACCOUNT</p>
          <nav aria-label="Account pages" className="nav-list">
            <NavLink
              aria-label="Settings"
              className={({ isActive }) => `nav-link${isActive ? ' nav-link-active' : ''}`}
              onClick={onCloseMobile}
              title={collapsed ? 'Settings' : undefined}
              to="/settings"
            >
              <Settings aria-hidden="true" size={19} strokeWidth={1.9} />
              <span>Settings</span>
            </NavLink>
            <button
              aria-label="Sign out"
              className="nav-link nav-signout"
              onClick={onSignOut}
              title={collapsed ? 'Sign out' : undefined}
              type="button"
            >
              <LogOut aria-hidden="true" size={19} strokeWidth={1.9} />
              <span>Sign out</span>
            </button>
          </nav>
        </div>

        <Link className="sidebar-account" onClick={onCloseMobile} title="Preview account; authentication is not connected yet" to="/settings">
          <span aria-hidden="true" className="account-avatar">F</span>
          <span className="account-copy">
            <strong>Farmer</strong>
            <small>Local preview</small>
          </span>
          <ChevronDown aria-hidden="true" className="account-chevron" size={16} />
        </Link>
      </aside>
    </>
  )
}
