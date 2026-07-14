from manim import *

class ScicracyAnimation(ThreeDScene):
    def construct(self):
        # Set dark, oppressive color scheme
        self.camera.background_color = "#1a1a2e"
        
        # 1. Dark parliamentary chamber (abstract)
        chamber = VGroup(
            Rectangle(width=14, height=8, color=BLUE_E, fill_opacity=0.3),
            *[Line(LEFT*6, RIGHT*6, color=GRAY, stroke_width=1) for _ in range(5)]
        ).shift(DOWN)
        self.add(chamber)
        
        # 2. Chains on documents (text)
        chains = Text("⛓️", font_size=36, color=GRAY).shift(LEFT*3 + DOWN*2)
        self.add(chains)
        
        # 3. Surveillance cameras (simple triangles)
        camera_icon = Triangle(color=RED).scale(0.3).shift(RIGHT*4 + UP*2)
        self.add(camera_icon)
        
        # 4. Book appears (materializing)
        book_cover = Rectangle(width=3, height=4, color=BLUE_D, fill_opacity=1, stroke_color=GOLD, stroke_width=4)
        title = Text("SCICRACY", font_size=28, color=GOLD).move_to(book_cover.get_center())
        amharic = Text("ማስጠና", font_size=20, color=GOLD).next_to(title, DOWN)
        book_group = VGroup(book_cover, title, amharic)
        book_group.move_to(ORIGIN).scale(0)  # start invisible
        
        self.play(Create(book_group), run_time=2)  # materialize
        self.play(book_group.animate.scale(1), run_time=1)
        
        # 5. Camera push-in (zoom)
        self.play(self.camera.frame.animate.scale(0.6).move_to(book_group), run_time=2)
        
        # 6. Book opens, pages flip
        left_page = Rectangle(width=1.5, height=3.5, color=WHITE, fill_opacity=1).shift(LEFT*0.8)
        right_page = Rectangle(width=1.5, height=3.5, color=WHITE, fill_opacity=1).shift(RIGHT*0.8)
        open_book = VGroup(left_page, right_page)
        self.play(Transform(book_group, open_book))
        
        # 7. Diagrams on pages
        network = VGroup(*[Dot(radius=0.05).shift(i*0.5*RIGHT + j*0.3*UP) for i in range(-2,3) for j in range(-2,3)])
        network.move_to(left_page.get_center())
        graph = Axes(x_range=[0,10], y_range=[0,10]).scale(0.4).move_to(right_page.get_center())
        fear_label = Text("Fear", color=RED).next_to(graph, LEFT)
        governance_label = Text("Self-Governance", color=GREEN).next_to(graph, RIGHT)
        
        self.play(Create(network), Create(graph), Write(fear_label), Write(governance_label))
        
        # 8. Hall cracks, sunlight pours in
        crack = Line(LEFT*5, RIGHT*5, color=YELLOW, stroke_width=8).shift(UP*2)
        sunlight = VGroup(*[Line(ORIGIN, direction, color=YELLOW, stroke_opacity=0.3) 
                           for direction in [DOWN+LEFT, DOWN, DOWN+RIGHT]])
        self.play(FadeIn(crack), FadeIn(sunlight))
        self.play(self.camera.background_color.animate.set_value("#3a2a1a"))  # warm amber shift
        
        # 9. Chains fall, people straighten
        self.play(FadeOut(chains), camera_icon.animate.scale(0), run_time=1)
        
        # 10. Final glowing text
        final_text = Text("ከእውራር ወደ ራስ-ገዝ ሥርዓት", font_size=36, color=GOLD, stroke_width=2)
        final_text.next_to(book_group, DOWN)
        self.play(Write(final_text))
        self.wait(2)