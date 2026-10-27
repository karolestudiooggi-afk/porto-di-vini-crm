import Image from "next/image";

type Variant = "branco" | "chumbo" | "auto";

const SRC = {
  branco: "/img/domani-horizontal-branco.png",
  chumbo: "/img/domani-horizontal-chumbo.png",
};

/**
 * variant="branco"  → sempre o logo branco (sobre fundos escuros)
 * variant="auto"    → chumbo no claro, branco no escuro (segue o tema)
 */
export function Logo({
  variant = "branco",
  className = "h-5 w-auto",
}: {
  variant?: Variant;
  className?: string;
}) {
  if (variant === "auto") {
    return (
      <>
        <Image src={SRC.chumbo} alt="Domani.AI" width={120} height={24} className={`${className} dark:hidden`} priority />
        <Image src={SRC.branco} alt="Domani.AI" width={120} height={24} className={`hidden ${className} dark:block`} priority />
      </>
    );
  }
  return <Image src={SRC[variant]} alt="Domani.AI" width={120} height={24} className={className} priority />;
}
