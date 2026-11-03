export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <button
      aria-checked={checked}
      aria-label={label}
      className={`relative inline-flex h-[22px] w-[38px] shrink-0 items-center rounded-full border transition ${checked ? "border-[#4c9b7a] bg-[#34785d]" : "border-white/[0.12] bg-[#262d35]"}`}
      onClick={onChange}
      role="switch"
      type="button"
    >
      <span className={`size-4 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-[18px]" : "translate-x-[3px]"}`} />
    </button>
  );
}
