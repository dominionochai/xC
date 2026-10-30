export type Preset = {
  id: string;
  label: string;
  acquirer: string;
  target: string;
};

export const PRESETS = [
  {
    id: "porsche-aime-leon-dore",
    label: "Porsche x Aimé Leon Dore",
    acquirer: "Porsche",
    target: "Aimé Leon Dore",
  },
  {
    id: "coachella-jacquemus",
    label: "Coachella x Jacquemus",
    acquirer: "Coachella",
    target: "Jacquemus",
  },
  {
    id: "lululemon-nfl",
    label: "Lululemon x NFL",
    acquirer: "Lululemon",
    target: "NFL",
  },
] as const satisfies readonly Preset[];
