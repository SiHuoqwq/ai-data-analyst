interface Props {
  content: string;
}

export default function UserMessage({ content }: Props) {
  return (
    <div className="flex justify-end mb-4">
      <div
        className="rounded-2xl px-4 py-2.5 max-w-[75%] text-sm leading-relaxed"
        style={{ background: '#2563eb', color: '#ffffff' }}
      >
        {content}
      </div>
    </div>
  );
}
