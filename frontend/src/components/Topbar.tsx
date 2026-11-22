import { useMemo, useState, type KeyboardEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  Bell,
  ChevronDown,
  ChevronRight,
  Menu,
  Moon,
  Search,
  Sun,
  UserRound,
  X,
} from 'lucide-react'
import { appNavigation, getPageLabel } from '../navigation'

type TopbarProps = {
  darkMode: boolean
  onToggleTheme: () => void
  onToggleSidebar: () => void
  onOpenMobileNav: () => void
  onNavigate: () => void
}

export function Topbar({
  darkMode,
  onToggleTheme,
  onToggleSidebar,
  onOpenMobileNav,
  onNavigate,
}: TopbarProps) {
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const page = getPageLabel(location.pathname)
  const results = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return []
    return appNavigation
      .filter((item) => `${item.label} ${item.description}`.toLowerCase().includes(normalized))
      .slice(0, 5)
  }, [query])

  function chooseFirstResult(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setSearchOpen(false)
      setQuery('')
    }
    if (event.key === 'Enter' && results[0]) {
      navigate(results[0].to)
      onNavigate()
      setQuery('')
      setSearchOpen(false)
    }
  }

  return (
    <header className="topbar">
      <div className="topbar-leading">
        <button
          aria-label="Toggle sidebar"
          className="topbar-icon-button desktop-sidebar-toggle"
          onClick={onToggleSidebar}
          title="Collapse or expand sidebar"
          type="button"
        >
          <Menu aria-hidden="true" size={20} />
        </button>
        <button
          aria-label="Open navigation"
          className="topbar-icon-button mobile-sidebar-toggle"
          onClick={onOpenMobileNav}
          type="button"
        >
          <Menu aria-hidden="true" size={21} />
        </button>
        <div aria-label={`Dashboard, ${page}`} className="breadcrumbs">
          <span>Dashboard</span>
          <ChevronRight aria-hidden="true" size={14} />
          <strong>{page}</strong>
        </div>
      </div>

      <div className="topbar-search-wrap">
        <div className="topbar-search">
          <Search aria-hidden="true" size={18} />
          <input
            aria-label="Search CropFarmAI"
            autoComplete="off"
            onBlur={() => window.setTimeout(() => setSearchOpen(false), 120)}
            onChange={(event) => {
              setQuery(event.target.value)
              setSearchOpen(true)
            }}
            onFocus={() => setSearchOpen(true)}
            onKeyDown={chooseFirstResult}
            placeholder="Search anything..."
            role="combobox"
            aria-expanded={searchOpen && query.trim().length > 0}
            aria-controls="global-search-results"
            value={query}
          />
          {query && (
            <button
              aria-label="Clear search"
              className="search-clear"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => setQuery('')}
              type="button"
            >
              <X size={15} />
            </button>
          )}
        </div>
        {searchOpen && query.trim() && (
          <div className="search-results" id="global-search-results" role="listbox">
            {results.length ? (
              results.map((item) => {
                const Icon = item.icon
                return (
                  <Link
                    className="search-result"
                    key={item.to}
                    onClick={() => {
                      onNavigate()
                      setQuery('')
                      setSearchOpen(false)
                    }}
                    role="option"
                    to={item.to}
                  >
                    <Icon aria-hidden="true" size={17} />
                    <span><strong>{item.label}</strong><small>{item.description}</small></span>
                    <ChevronRight aria-hidden="true" size={15} />
                  </Link>
                )
              })
            ) : (
              <p className="search-no-results">No matching pages. Farm records will be searchable after data is connected.</p>
            )}
          </div>
        )}
      </div>

      <div className="topbar-actions">
        <div className="popover-anchor">
          <button
            aria-expanded={notificationsOpen}
            aria-label="Notifications; no unread notifications"
            className={`topbar-icon-button notification-trigger${notificationsOpen ? ' icon-button-selected' : ''}`}
            onClick={() => {
              setNotificationsOpen((open) => !open)
              setProfileOpen(false)
            }}
            type="button"
          >
            <Bell aria-hidden="true" size={19} />
          </button>
          {notificationsOpen && (
            <div className="header-popover notification-popover">
              <div className="popover-heading"><strong>Notifications</strong><span>0 unread</span></div>
              <div className="notification-empty">
                <span className="empty-bell"><Bell aria-hidden="true" size={20} /></span>
                <strong>You’re all caught up</strong>
                <p>Notifications will appear here when activity is connected.</p>
              </div>
            </div>
          )}
        </div>
        <button
          aria-label={darkMode ? 'Switch to light theme' : 'Switch to dark theme'}
          className="topbar-icon-button theme-toggle"
          onClick={onToggleTheme}
          title={darkMode ? 'Use light theme' : 'Use dark theme'}
          type="button"
        >
          {darkMode ? <Sun aria-hidden="true" size={19} /> : <Moon aria-hidden="true" size={19} />}
        </button>
        <div className="popover-anchor">
          <button
            aria-expanded={profileOpen}
            aria-label="Open profile menu"
            className={`profile-trigger${profileOpen ? ' profile-trigger-open' : ''}`}
            onClick={() => {
              setProfileOpen((open) => !open)
              setNotificationsOpen(false)
            }}
            type="button"
          >
            <span aria-hidden="true" className="profile-avatar"><UserRound size={18} /></span>
            <span className="profile-trigger-copy"><strong>Farmer</strong><small>Preview</small></span>
            <ChevronDown aria-hidden="true" size={15} />
          </button>
          {profileOpen && (
            <div className="header-popover profile-popover">
              <div className="profile-popover-title"><span className="profile-avatar"><UserRound size={17} /></span><span><strong>Local preview</strong><small>No account signed in</small></span></div>
              <Link className="popover-link" onClick={() => { setProfileOpen(false); onNavigate() }} to="/settings">Profile and settings <ChevronRight size={15} /></Link>
              <Link className="popover-link" onClick={() => { setProfileOpen(false); onNavigate() }} to="/login">Authentication setup <ChevronRight size={15} /></Link>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
