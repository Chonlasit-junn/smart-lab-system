export default function SmartLabLogo({ decorative = false }) {
  return (
    <img
      className="smart-lab-logo"
      src={`${import.meta.env.BASE_URL}smart-lab-logo.png`}
      alt={decorative ? "" : "Smart Lab"}
      width={44}
      height={44}
    />
  );
}
