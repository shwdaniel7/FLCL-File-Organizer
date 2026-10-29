from .activity import ActivityPage
from .organize import OrganizePage
from .reports import ReportsPage
from .rules import RulesPage
from .settings import SettingsPage

# key, icon, nav label, title, subtitle, page class
PAGES = [
    ("organize", "organize", "Organize", "Organize", "Preview every move before anything changes.", OrganizePage),
    ("activity", "activity", "Activity", "Activity", "Live status and everything the organizer did.", ActivityPage),
    ("reports", "reports", "Reports", "Reports", "What has been organized, where, and how much space it takes.", ReportsPage),
    ("rules", "rules", "Rules", "Rules", "Decide where each kind of file goes.", RulesPage),
    ("settings", "settings", "Settings", "Settings", "Behavior, appearance and shortcuts.", SettingsPage),
]
