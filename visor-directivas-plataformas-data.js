window.PLATFORM_DIRECTIVES_DATA = {
  meta: {
    title: "Visor de Comités por Plataforma",
    description:
      "Seguimiento rapido para identificar el encargado de cada plataforma y si ya tiene comité elegido.",
    updatedAt: "2026-08-31",
    source: "Capturas compartidas por WhatsApp el 31 de agosto de 2026.",
    notes: [
      "Actualizacion manual aplicada: las plataformas L y P tambien se marcan con comité elegido.",
      "La plataforma E no aparece en las capturas recibidas; se deja visible como pendiente de confirmacion."
    ]
  },
  platforms: [
    { code: "A", label: "Plataforma A", manager: "Marco Miñaca", assignedAt: "2026-07-20", status: "pending" },
    {
      code: "B",
      label: "Plataforma B",
      manager: "Diego Layedra",
      assignedAt: "2026-08-11",
      status: "selected",
      committee: [
        { role: "Coordinador", name: "Nicolás Taipe", phone: "0984572317" },
        { role: "Secretario", name: "Dr. Hernán Garcés", phone: "0984965116" },
        { role: "Primer vocal principal", name: "Galo Paña", phone: "0995229403" },
        { role: "Segundo vocal principal", name: "Betty Guaraca", phone: "0983078783" }
      ]
    },
    { code: "C", label: "Plataforma C", manager: "Jessica Guamán", assignedAt: "2026-08-25", status: "pending" },
    { code: "D", label: "Plataforma D", manager: "Juan Diego Remache", assignedAt: "2026-08-21", status: "pending" },
    { code: "E", label: "Plataforma E", manager: null, assignedAt: null, status: "unknown" },
    { code: "F", label: "Plataforma F", manager: "Danny Usca", assignedAt: "2026-08-12", status: "selected" },
    { code: "G", label: "Plataforma G", manager: "Sandra Guevara", assignedAt: "2026-08-31", status: "pending" },
    { code: "H", label: "Plataforma H", manager: "Fabián Codel", assignedAt: "2026-08-14", status: "selected" },
    { code: "I", label: "Plataforma I", manager: "Mauricio Pérez", assignedAt: "2026-08-21", status: "pending" },
    { code: "J", label: "Plataforma J", manager: "Fabián Borja", assignedAt: "2026-08-24", status: "pending" },
    {
      code: "K",
      label: "Plataforma K",
      manager: "Fernanda Vasco y Sebastián López",
      assignedAt: "2026-08-27",
      status: "selected",
      committee: [
        { role: "Presidencia", name: "María del Carmen Gallegos", phone: "0988952797" },
        { role: "Vicepresidencia", name: "Ing. Jorge López Sena", phone: "0984763415" },
        { role: "Secretaría", name: "Miriam López", phone: "0990839018" },
        { role: "Vocal 1. Eje Plan", name: "Alberto Villa" },
        { role: "Vocal 2. Eje Gestión", name: "Mirian Silva", phone: "0995512722" },
        { role: "Vocal 3. Eje Gobernanza", name: "Dr. Sergio Flores" }
      ]
    },
    { code: "L", label: "Plataforma L", manager: "Alexis Pumagualli", assignedAt: "2026-08-14", status: "selected" },
    { code: "M", label: "Plataforma M", manager: "Alejandro Ríos", assignedAt: "2026-08-18", status: "selected" },
    { code: "N", label: "Plataforma N", manager: "Luis Vásquez", assignedAt: "2026-08-20", status: "pending" },
    {
      code: "Ñ",
      label: "Plataforma Ñ",
      manager: "Andres Vazques",
      assignedAt: "2026-08-19",
      status: "selected",
      committee: [
        { role: "Presidencia", name: "María Tenelema", phone: "0980086272" },
        { role: "Vicepresidencia", name: "Truman Tapia" },
        { role: "Secretaría", name: "Prisila Tello Hinojosa", phone: "0989006726" },
        { role: "Vocal 1. Eje Plan", name: "Juana Estrada", phone: "0987071198" },
        { role: "Vocal 2. Eje Gestión", name: "Yolanda León" },
        { role: "Vocal 3. Eje Gobernanza", name: "Germania Borja", phone: "0998940921" },
        { role: "Vocal 4. Eje Resiliencia", name: "Carol Tovar Molina", phone: "0969293972" }
      ]
    },
    {
      code: "O",
      label: "Plataforma O",
      manager: "Ramiro Vallejo",
      assignedAt: "2026-08-11",
      status: "selected",
      committee: [
        { role: "Coordinador", name: "Hugo Mariño" },
        { role: "Coordinadora", name: "Olga Uquillas", phone: "0967499180" },
        { role: "Coordinador", name: "Luis Albán", phone: "0984631389" },
        { role: "Coordinador", name: "Armando Coloma" },
        { role: "Coordinadora", name: "Marian Gavidia", phone: "0983305953" },
        { role: "Coordinador", name: "Washington Machado" },
        { role: "Coordinadora", name: "Mariana Calderón" },
        { role: "Coordinadora", name: "Mercedes Jamín", phone: "0986958998" }
      ]
    },
    { code: "P", label: "Plataforma P", manager: "Silvana Vásquez", assignedAt: "2026-08-12", status: "selected" },
    {
      code: "Q",
      label: "Plataforma Q",
      manager: "Christian Tello",
      assignedAt: "2026-08-20",
      status: "selected",
      committee: [
        { role: "Presidencia", name: "Milton Pazmiño Novillo", phone: "0993888329" },
        { role: "Vicepresidencia", name: "Rosa Elvira Tello Noboa", phone: "0974602641" },
        { role: "Secretaría", name: "Miguel Vinicio Zúñiga Brito", phone: "0984856020" }
      ]
    }
  ]
};
