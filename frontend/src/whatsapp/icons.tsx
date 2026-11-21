import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement>;

const base = (props: IconProps) => ({
  viewBox: '0 0 24 24',
  width: 24,
  height: 24,
  'aria-hidden': true,
  focusable: false,
  ...props,
});

export const BackIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path fill="currentColor" d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
  </svg>
);

export const VideoIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z"
    />
  </svg>
);

export const PhoneIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M6.62 10.79a15.05 15.05 0 0 0 6.59 6.59l2.2-2.2a1 1 0 0 1 1.02-.24c1.12.37 2.33.57 3.57.57a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1.02l-2.2 2.2z"
    />
  </svg>
);

export const MenuIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M12 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm0 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"
    />
  </svg>
);

export const EmojiIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm-3.5-9a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zm7 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM12 17.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z"
    />
  </svg>
);

export const AttachIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M16.5 6.5v10.25a4.5 4.5 0 0 1-9 0V5.5a3 3 0 0 1 6 0v10.25a1.5 1.5 0 0 1-3 0V6.5H9v9.25a3 3 0 0 0 6 0V5.5a4.5 4.5 0 0 0-9 0v11.25a6 6 0 0 0 12 0V6.5h-1.5z"
    />
  </svg>
);

export const CameraIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM9 2 7.17 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-3.17L15 2H9zm3 15a5 5 0 1 1 0-10 5 5 0 0 1 0 10z"
    />
  </svg>
);

export const MicIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5.3-3a5.3 5.3 0 0 1-10.6 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-1.7z"
    />
  </svg>
);

export const SendIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path fill="currentColor" d="M3.4 20.4 21 12 3.4 3.6 3.4 10l12.6 2-12.6 2z" />
  </svg>
);

export const ReplyIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path fill="currentColor" d="M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z" />
  </svg>
);

export const ForwardIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path fill="currentColor" d="M14 9V5l7 7-7 7v-4.1c-5 0-8.5 1.6-11 5.1 1-5 4-10 11-11z" />
  </svg>
);

export const CloseIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"
    />
  </svg>
);

export const ChainIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zm-7 12h-2v-2h2v2zm0-4h-2V6h2v4z"
    />
  </svg>
);

export const ExternalLinkIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"
    />
  </svg>
);

export const LockIcon = (props: IconProps) => (
  <svg {...base(props)}>
    <path
      fill="currentColor"
      d="M18 8h-1V6A5 5 0 0 0 7 6v2H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2zM9 6a3 3 0 0 1 6 0v2H9V6zm3 11a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"
    />
  </svg>
);

export const ClockIcon = (props: IconProps) => (
  <svg {...base({ viewBox: '0 0 16 16', width: 14, height: 14, ...props })}>
    <path
      fill="currentColor"
      d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zm0 11.7a5.2 5.2 0 1 1 0-10.4 5.2 5.2 0 0 1 0 10.4zM8.6 4.6H7.4v4l3.2 1.9.6-1-2.6-1.5V4.6z"
    />
  </svg>
);

export const TickIcon = (props: IconProps) => (
  <svg {...base({ viewBox: '0 0 16 11', width: 16, height: 11, ...props })}>
    <path fill="currentColor" d="M11.07.65 4.4 7.32 1.55 4.47.47 5.55 4.4 9.48l7.75-7.75z" />
  </svg>
);

export const DoubleTickIcon = (props: IconProps) => (
  <svg {...base({ viewBox: '0 0 16 11', width: 16, height: 11, ...props })}>
    <path
      fill="currentColor"
      d="M11.07.65 4.4 7.32 1.55 4.47.47 5.55 4.4 9.48l7.75-7.75zm3.46 0L7.86 7.32l-.7-.7-1.08 1.08 1.78 1.78 7.75-7.75z"
    />
  </svg>
);

export const FailedIcon = (props: IconProps) => (
  <svg {...base({ viewBox: '0 0 16 16', width: 15, height: 15, ...props })}>
    <circle cx="8" cy="8" r="7" fill="currentColor" />
    <path fill="#fff" d="M7.2 3.8h1.6v5.4H7.2zM7.2 10.6h1.6v1.6H7.2z" />
  </svg>
);

// SprawdzTo avatar: a magnifying glass with a check mark.
export const SprawdzToAvatar = ({ size = 40 }: { size?: number }) => (
  <svg viewBox="0 0 40 40" width={size} height={size} aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id="sprawdzto-avatar" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#2dd4bf" />
        <stop offset="1" stopColor="#0f766e" />
      </linearGradient>
    </defs>
    <circle cx="20" cy="20" r="20" fill="url(#sprawdzto-avatar)" />
    <circle cx="18" cy="18" r="8.5" fill="none" stroke="#fff" strokeWidth="2.6" />
    <path d="m24.2 24.2 6.3 6.3" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
    <path
      d="m14.3 18.2 2.7 2.7 4.9-5.4"
      fill="none"
      stroke="#fff"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
