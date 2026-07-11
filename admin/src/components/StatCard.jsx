export default function StatCard({ icon: Icon, label, value, trend }) {
    return (
        <div className="card p-5 flex flex-col gap-3">
            {/* Icon */}
            <div className="w-9 h-9 rounded-lg bg-bg-tertiary flex items-center justify-center">
                <Icon className="w-4 h-4 text-text-secondary" />
            </div>

            {/* Value */}
            <div>
                <p className="text-2xl font-semibold text-text-primary tracking-tight">{value}</p>
                <p className="text-xs text-text-muted mt-0.5">{label}</p>
            </div>

            {/* Optional trend */}
            {trend && (
                <p className={`text-xs font-medium ${trend > 0 ? 'text-success' : 'text-danger'}`}>
                    {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}% from last month
                </p>
            )}
        </div>
    )
}
