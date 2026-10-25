import { Link } from 'react-router-dom';
import '../styles/footer.css';

/**
 * SiteFooter - Shared, reusable footer component across all active Astrograph routes.
 * 
 * Props:
 *  - compact (boolean): When true, renders a sleek, space-saving variant for dense views like Workspace.
 *  - className (string): Optional additional classes.
 */
export default function SiteFooter({ compact = false, className = '' }) {
  const currentYear = new Date().getFullYear();

  return (
    <footer
      className={`astro-site-footer ${compact ? 'astro-site-footer--compact' : ''} ${className}`}
      aria-label="Site Footer"
    >
      <div className="astro-site-footer__inner">
        {/* Left: Official Brand Logo, Title, and Celestial Tagline */}
        <div className="astro-site-footer__brand-block">
          <Link to="/" className="astro-site-footer__brand-link" title="Astrograph Home">
            <img
              src="/team_logo_transparent.png"
              alt="Astrograph Logo"
              className="astro-site-footer__logo"
              draggable="false"
            />
            <span className="astro-site-footer__brand-name">A S T R O G R A P H</span>
          </Link>
          <span className="astro-site-footer__divider" aria-hidden="true" />
          <span className="astro-site-footer__tagline">
            Visualize · Understand · Build Better.
          </span>
        </div>

        {/* Right: Navigation Links and Dynamic Copyright */}
        <div className="astro-site-footer__right-block">
          <nav className="astro-site-footer__nav" aria-label="Footer Navigation">
            <Link to="/" className="astro-site-footer__nav-link">
              Home
            </Link>
            <Link to="/features" className="astro-site-footer__nav-link">
              Features
            </Link>
            <Link to="/about" className="astro-site-footer__nav-link">
              About
            </Link>
          </nav>

          <span className="astro-site-footer__copyright">
            © {currentYear} Astrograph. All rights reserved.
          </span>
        </div>
      </div>
    </footer>
  );
}
