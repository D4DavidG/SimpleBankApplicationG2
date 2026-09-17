/* A text field whose contents are hidden, with an eye to reveal them.
 *
 * Hiding what you type stops somebody reading it over your shoulder; it does
 * nothing else, and it is a common cause of typos in exactly the fields where a
 * typo is most annoying. Letting people look is the usual fix.
 *
 * The toggle is a real <button type="button">. Without the type it would default
 * to "submit" and revealing the password would send the form.
 */
import { useState } from 'react'

// `ref` is taken as an ordinary prop and handed to the input. React 19 allows
// that directly; before 19 this needed forwardRef.
export default function SecretInput({ label, value, onChange, hint, ref, ...rest }) {
  const [revealed, setRevealed] = useState(false)

  return (
    <label>
      {label}
      <span className="secret-field">
        <input
          ref={ref}
          type={revealed ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          {...rest}
        />
        <button
          type="button"
          className="reveal"
          onClick={() => setRevealed(!revealed)}
          /* The control is an icon, so it needs a name of its own for anyone not
           * looking at it. aria-pressed is what says which way it is currently
           * set - "Show" alone would not tell a screen reader it is a toggle. */
          aria-label={revealed ? 'Hide' : 'Show'}
          aria-pressed={revealed}
        >
          {revealed ? '🙈' : '👁'}
        </button>
      </span>
      {hint && <span className="hint">{hint}</span>}
    </label>
  )
}
