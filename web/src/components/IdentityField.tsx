export const IdentityField = ({ label, value, mono = false, note }: { label: string; value: string; mono?: boolean; note?: string }) => (
  <div className="identity-field">
    <span className="field-label">{label}</span>
    <strong className={mono ? "mono" : ""} title={value}>{value}</strong>
    {note && <small>{note}</small>}
  </div>
);
