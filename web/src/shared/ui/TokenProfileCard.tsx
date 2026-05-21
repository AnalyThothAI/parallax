import type { TokenProfileBlock } from "@lib/types";
import clsx from "clsx";
import { ExternalLink, Globe, MessageCircle, Search } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import "./shared.css";

type TokenProfileCardProps = {
  profile?: TokenProfileBlock | null;
  compact?: boolean;
};

type TokenProfileLinksProps = {
  ariaLabel?: string;
  compact?: boolean;
  includeLabels?: string[];
  links?: TokenProfileBlock["links"] | null;
  maxLinks?: number;
};

type ProfileLink = {
  label: string;
  href: string;
  Icon: LucideIcon;
};

const LOCAL_LOGO_PREFIX = "/api/" + "token-images/";

export function TokenProfileCard({ profile, compact = false }: TokenProfileCardProps) {
  if (!profile || normalizedStatus(profile) !== "ready") {
    return <TokenProfileState compact={compact} profile={profile} />;
  }

  const identity = profile.identity ?? {};
  const linksBlock = profile.links ?? {};
  const source = profile.source ?? {};
  const name = cleanText(identity.name) ?? cleanText(identity.symbol) ?? "Unknown";
  const symbol = cleanText(identity.symbol);
  const description = cleanText(identity.description);
  const logoUrl = localLogoUrl(identity.logo_url);
  const provider = cleanText(profile.provider) ?? cleanText(source.provider);
  const twitterUsername = twitterUsernameText(linksBlock.twitter_username);

  return (
    <section
      aria-label="Token profile"
      className={clsx("token-profile-card", "is-ready", compact && "is-compact")}
    >
      <div className="token-profile-main">
        {logoUrl ? (
          <img alt={`${name} logo`} className="token-profile-logo" src={logoUrl} />
        ) : (
          <div className="token-profile-logo-placeholder" aria-hidden>
            <Search />
          </div>
        )}
        <div className="token-profile-copy">
          <div className="token-profile-title">
            <h3>{name}</h3>
            {symbol ? <code>${symbol}</code> : null}
          </div>
          {description ? <p>{description}</p> : null}
          {provider || twitterUsername ? (
            <div className="token-profile-meta">
              {provider ? <small>{provider}</small> : null}
              {twitterUsername ? <small>{twitterUsername}</small> : null}
            </div>
          ) : null}
        </div>
      </div>

      <TokenProfileLinks links={linksBlock} />
    </section>
  );
}

export function TokenProfileLinks({
  ariaLabel = "Token profile links",
  compact = false,
  includeLabels,
  links,
  maxLinks,
}: TokenProfileLinksProps) {
  const linksBlock = links ?? {};
  const twitterUsername = twitterUsernameText(linksBlock.twitter_username);
  const includedLabels = includeLabels ? new Set(includeLabels) : null;
  const profileLinks = buildProfileLinks(linksBlock, twitterUsername).filter((item) =>
    includedLabels ? includedLabels.has(item.label) : true,
  );
  const visibleLinks = maxLinks ? profileLinks.slice(0, maxLinks) : profileLinks;

  if (!visibleLinks.length) {
    return null;
  }

  return (
    <nav className={clsx("token-profile-links", compact && "is-compact")} aria-label={ariaLabel}>
      {visibleLinks.map(({ label, href, Icon }) => (
        <a href={href} key={label} rel="noreferrer" target="_blank">
          <Icon aria-hidden />
          <span>{label}</span>
        </a>
      ))}
    </nav>
  );
}

function TokenProfileState({
  compact,
  profile,
}: {
  compact: boolean;
  profile?: TokenProfileBlock | null;
}) {
  const status = normalizedStatus(profile);
  const source = profile?.source ?? {};
  const provider = cleanText(profile?.provider) ?? cleanText(source.provider);
  const lastError = status === "error" ? cleanText(source.last_error) : null;
  const message = profileStateMessage(status);

  return (
    <section
      aria-label="Token profile"
      className={clsx(
        "token-profile-card",
        "is-muted",
        status === "error" && "is-error",
        compact && "is-compact",
      )}
    >
      <div className="token-profile-state">
        <Search aria-hidden />
        <div>
          <strong>{message}</strong>
          {lastError ? <small>{lastError}</small> : provider ? <small>{provider}</small> : null}
        </div>
      </div>
    </section>
  );
}

function buildProfileLinks(
  links: NonNullable<TokenProfileBlock["links"]>,
  twitterUsername: string | null,
): ProfileLink[] {
  return [
    { label: "Website", href: cleanText(links.website_url), Icon: Globe },
    {
      label: "X",
      href: cleanText(links.twitter_url) ?? twitterHref(twitterUsername),
      Icon: ExternalLink,
    },
    { label: "Telegram", href: cleanText(links.telegram_url), Icon: MessageCircle },
    { label: "GMGN", href: cleanText(links.gmgn_url), Icon: Search },
    { label: "GeckoTerminal", href: cleanText(links.geckoterminal_url), Icon: ExternalLink },
  ].filter((item): item is ProfileLink => Boolean(item.href));
}

function localLogoUrl(value?: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed?.startsWith(LOCAL_LOGO_PREFIX) ? trimmed : null;
}

function twitterUsernameText(value?: string | null): string | null {
  const username = cleanText(value)?.replace(/^@+/, "");
  return username ? `@${username}` : null;
}

function twitterHref(value: string | null): string | null {
  const username = value?.replace(/^@+/, "");
  return username ? `https://x.com/${encodeURIComponent(username)}` : null;
}

function normalizedStatus(profile?: TokenProfileBlock | null): string {
  return cleanText(profile?.status)?.toLowerCase() ?? "unavailable";
}

function profileStateMessage(status: string): string {
  if (status === "pending") return "profile pending";
  if (status === "missing") return "profile not found";
  if (status === "unsupported") return "profile unsupported";
  if (status === "error") return "profile refresh error";
  if (status === "unavailable") return "profile unavailable";
  return `profile ${status}`;
}

function cleanText(value?: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}
