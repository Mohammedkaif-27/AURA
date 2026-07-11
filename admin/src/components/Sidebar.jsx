import { NavLink } from 'react-router-dom'
import {
    LayoutDashboard,
    Package,
    ShoppingCart,
    Brain,
    Shield,
    Radio,
    ChevronLeft,
    ChevronRight,
} from 'lucide-react'

const navItems = [
    { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/inventory', icon: Package, label: 'Inventory' },
    { to: '/orders', icon: ShoppingCart, label: 'Orders' },
    { to: '/knowledge', icon: Brain, label: 'Knowledge' },
    { to: '/policies', icon: Shield, label: 'Policies' },
    { to: '/live', icon: Radio, label: 'Live Center' },
]

export default function Sidebar({ open, onToggle }) {
    return (
        <aside
            className={`
        relative flex flex-col h-full bg-bg border-r border-border
        transition-all duration-200 ease-in-out shrink-0
        ${open ? 'w-56' : 'w-[60px]'}
      `}
        >
            {/* Brand */}
            <div className="flex items-center gap-3 px-4 py-5 border-b border-border">
                <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center shrink-0">
                    <span className="text-white text-sm font-bold">A</span>
                </div>
                {open && (
                    <div className="animate-fade-in overflow-hidden">
                        <h1 className="text-sm font-semibold text-text-primary leading-none">
                            AURA
                        </h1>
                        <p className="text-xs text-text-muted mt-0.5">Admin</p>
                    </div>
                )}
            </div>

            {/* Navigation */}
            <nav className="flex-1 py-3 px-2 space-y-0.5">
                {navItems.map(({ to, icon: Icon, label }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={to === '/'}
                        className={({ isActive }) =>
                            `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors
              ${isActive
                                ? 'bg-accent-light text-accent'
                                : 'text-text-secondary hover:text-text-primary hover:bg-bg-secondary'
                            }`
                        }
                    >
                        <Icon className="w-4 h-4 shrink-0" />
                        {open && <span className="animate-fade-in truncate">{label}</span>}
                    </NavLink>
                ))}
            </nav>

            {/* Collapse toggle */}
            <button
                onClick={onToggle}
                className="flex items-center justify-center mx-2 mb-4 h-8 rounded-lg
                   border border-border text-text-muted
                   hover:text-text-primary hover:bg-bg-secondary transition-colors"
                title={open ? 'Collapse sidebar' : 'Expand sidebar'}
            >
                {open ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
        </aside>
    )
}
