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
    { code: "A", label: "Plataforma A", manager: "Cnel. Marco Miñaca", assignedAt: "2026-07-20", status: "pending" },
    {
      code: "B",
      label: "Plataforma B",
      manager: "Ing. Diego Layedra",
      assignedAt: "2026-08-11",
      status: "selected",
      committee: [
        { role: "Coordinador", name: "Nicolás Taipe", phone: "0984572317" },
        { role: "Secretario", name: "Dr. Hernán Garcés", phone: "0984965116" },
        { role: "Primer vocal principal", name: "Galo Paña", phone: "0995229403" },
        { role: "Segundo vocal principal", name: "Betty Guaraca", phone: "0983078783" }
      ]
    },
    { code: "C", label: "Plataforma C", manager: "Ing. Jessica Guamán", assignedAt: "2026-08-25", status: "pending" },
    { code: "D", label: "Plataforma D", manager: "Ing. Juan Diego Remache", assignedAt: "2026-08-21", status: "pending" },
    { code: "E", label: "Plataforma E", manager: null, assignedAt: null, status: "unknown" },
    { code: "F", label: "Plataforma F", manager: "Ing. Danny Usca", assignedAt: "2026-08-12", status: "selected" },
    { code: "G", label: "Plataforma G", manager: "Mgs. Sandra Guevara", assignedAt: "2026-08-31", status: "pending" },
    { code: "H", label: "Plataforma H", manager: "Cnel. Fabian Codel", assignedAt: "2026-08-14", status: "selected" },
    { code: "I", label: "Plataforma I", manager: "Mgs. Mauricio Perez", assignedAt: "2026-08-21", status: "pending" },
    { code: "J", label: "Plataforma J", manager: "Cnel. Fabian Codel", assignedAt: "2026-08-24", status: "pending" },
    { code: "K", label: "Plataforma K", manager: "Arq. Fernanda Vasco", assignedAt: "2026-08-27", status: "selected" },
    { code: "L", label: "Plataforma L", manager: "Ing. Alexis Pumagualli", assignedAt: "2026-08-14", status: "selected" },
    { code: "M", label: "Plataforma M", manager: "Ing. Alejandro Rios", assignedAt: "2026-08-18", status: "pending" },
    { code: "N", label: "Plataforma N", manager: "Ing. Luis Vasquez", assignedAt: "2026-08-20", status: "pending" },
    { code: "Ñ", label: "Plataforma Ñ", manager: "Arq. Christian Tello", assignedAt: "2026-08-19", status: "pending" },
    { code: "O", label: "Plataforma O", manager: "Abg. Ramiro Vallejo", assignedAt: "2026-08-11", status: "selected" },
    { code: "P", label: "Plataforma P", manager: "Ing. Silvana Vasquez", assignedAt: "2026-08-12", status: "selected" },
    { code: "Q", label: "Plataforma Q", manager: "Arq. Christian Tello", assignedAt: "2026-08-20", status: "pending" }
  ]
};
