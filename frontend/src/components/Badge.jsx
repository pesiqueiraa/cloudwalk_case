const TONES = {
  open: "blue", escalated: "amber", closed: "gray",
  agent: "green", human: "violet", high: "red", normal: "gray",
};

export default function Badge({ value, label }) {
  if (!value) return null;
  return <span className={`badge badge-${TONES[value] ?? "gray"}`}>{label ?? value}</span>;
}
