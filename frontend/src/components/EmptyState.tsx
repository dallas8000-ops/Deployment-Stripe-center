interface EmptyStateProps {
  icon: string;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
    disabled?: boolean;
  };
  helpText?: string;
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
  helpText,
}: EmptyStateProps) {
  return (
    <div className="empty-state-container">
      <div className="empty-state-icon">{icon}</div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-description">{description}</p>
      {action && (
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={action.onClick}
          disabled={action.disabled}
        >
          {action.label}
        </button>
      )}
      {helpText && <p className="empty-state-help">{helpText}</p>}
    </div>
  );
}
