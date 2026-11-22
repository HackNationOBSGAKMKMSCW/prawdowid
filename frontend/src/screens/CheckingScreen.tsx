export default function CheckingScreen() {
  return (
    <div className="page page--center page--checking">
      <span className="spinner" aria-hidden="true" />
      <h1 className="title-l" tabIndex={-1}>
        Sprawdzamy…
      </h1>
      <p className="lead">To potrwa kilka sekund.</p>
    </div>
  );
}
