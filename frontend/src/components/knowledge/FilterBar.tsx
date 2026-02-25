interface FilterBarProps {
  type: string;
  onTypeChange: (type: string) => void;
}

const TYPES = ['all', 'decision', 'change', 'approval', 'blocker'];

export default function FilterBar({ type, onTypeChange }: FilterBarProps) {
  return (
    <div className="flex gap-2 flex-wrap">
      {TYPES.map((t) => (
        <button
          key={t}
          onClick={() => onTypeChange(t === 'all' ? '' : t)}
          className={`text-sm px-3 py-1 rounded-full border transition-colors ${
            (type === '' && t === 'all') || type === t
              ? 'bg-gray-900 text-white border-gray-900'
              : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-100'
          }`}
        >
          {t.charAt(0).toUpperCase() + t.slice(1)}
        </button>
      ))}
    </div>
  );
}
