export default function BrandLogo({ className = "", size = "normal" }) {
  const isLarge = size === "large";

  return (
    <div className={`flex items-center gap-2.5 select-none shrink-0 ${className}`}>
      {/* Modern surveillance eye badge */}
      <div
        className={`relative flex items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 via-indigo-600 to-sky-500 text-white shadow-lg shadow-blue-500/20 ring-1 ring-white/15 group-hover:shadow-blue-500/40 group-hover:scale-105 transition duration-200 ${
          isLarge ? "w-10 h-10" : "w-8 h-8"
        }`}
      >
        <svg
          className={`${isLarge ? "w-5 h-5" : "w-4 h-4"} text-sky-100 drop-shadow`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {/* Outer eye contour */}
          <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
          {/* Iris */}
          <circle cx="12" cy="12" r="3" fill="currentColor" fillOpacity="0.25" />
          {/* Pupil center */}
          <circle cx="12" cy="12" r="1.2" fill="currentColor" />
        </svg>
      </div>

      {/* Brand typography */}
      <span
        className={`font-black uppercase tracking-wider text-white flex items-center gap-1.5 ${
          isLarge ? "text-lg" : "text-sm"
        }`}
      >
        <span className="tracking-widest text-slate-100 drop-shadow-sm">VIRTUAL</span>
        <span className="bg-gradient-to-r from-blue-400 via-sky-300 to-cyan-400 bg-clip-text text-transparent font-black tracking-widest drop-shadow">
          EYE
        </span>
      </span>
    </div>
  );
}

