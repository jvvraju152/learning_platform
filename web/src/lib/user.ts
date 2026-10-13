import { useOutletContext } from "react-router-dom"

export const useUser = () => useOutletContext<{ user: any }>().user
