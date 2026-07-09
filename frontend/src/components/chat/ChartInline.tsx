interface Props {
  path: string;
}

export default function ChartInline({ path }: Props) {
  return (
    <div className="my-2">
      <img
        src={path}
        alt="Chart"
        className="max-h-80 rounded-lg border cursor-pointer transition-opacity hover:opacity-90"
        style={{ borderColor: '#334155', background: '#ffffff' }}
        onClick={() => window.open(path, '_blank')}
      />
    </div>
  );
}
