type Props = {
  steps: string[];
  title?: string;
};

export default function DeployNextSteps({ steps, title = "Next steps" }: Props) {
  if (!steps.length) return null;

  return (
    <section className="card next-steps-card">
      <h2>{title}</h2>
      <ol className="next-steps-list">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </section>
  );
}
