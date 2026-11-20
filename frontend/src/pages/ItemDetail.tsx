import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { type Item, api } from '../api.ts';

export default function ItemDetail() {
  const { id = '' } = useParams();
  const [item, setItem] = useState<Item | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getItem(id)
      .then(setItem)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  return (
    <>
      <p>
        <Link to="/items">&larr; Back</Link>
      </p>
      {error && <p className="error">{error}</p>}
      {item && (
        <>
          <h1>{item.name}</h1>
          <p>ID: {item.id}</p>
        </>
      )}
    </>
  );
}
