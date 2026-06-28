type PanelProps = {
  readonly title: string;
};

export function Panel({ title }: PanelProps) {
  return (
    <section>
      <h1>{title}</h1>
      <p>row one</p>
      <p>row two</p>
      <p>row three</p>
      <p>row four</p>
      <p>row five</p>
      <output>done</output>
    </section>
  );
}
