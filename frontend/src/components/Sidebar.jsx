import { Icon } from './Icons.jsx'

const navigation = [
  { id: 'dashboard', label: 'Overview', icon: 'dashboard' },
  { id: 'video-analysis', label: 'Video analysis', icon: 'upload' },
  { id: 'monitoring', label: 'Live monitoring', icon: 'camera' },
  { id: 'history', label: 'Recent alerts', icon: 'history' },
  { id: 'settings', label: 'Settings', icon: 'settings' },
]

function Sidebar({ activeSection, onNavigate }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark"><Icon name="brand" /></span>
        <span>SecureVoice <span>AI</span></span>
      </div>

      <p className="workspace-label">WORKSPACE</p>
      <nav className="side-nav" aria-label="Main navigation">
        {navigation.map(({ id, label, icon }) => (
          <button
            aria-current={activeSection === id ? 'page' : undefined}
            className={`nav-item${activeSection === id ? ' active' : ''}`}
            key={id}
            onClick={() => onNavigate(id)}
            type="button"
          >
            <Icon name={icon} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="home-card">
          <div className="home-card-top"><Icon name="shield" /> Secure workspace</div>
          <p>Person-entry events only</p>
        </div>
        <p className="sidebar-disclaimer">This prototype is not a substitute for a professional security system.</p>
      </div>
    </aside>
  )
}

export default Sidebar
